[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,

    [ValidateSet('Inventory', 'MirrorRecovery')]
    [string]$Mode = 'Inventory',

    [switch]$IncludeHashes,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Log {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet('INFO','WARN','ERROR')][string]$Level = 'INFO'
    )
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
    Add-Content -LiteralPath $script:LogPath -Value $line
}

function Ensure-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-SafeRelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$FullPath
    )
    $rootResolved = [System.IO.Path]::GetFullPath($Root)
    $fullResolved = [System.IO.Path]::GetFullPath($FullPath)

    if (-not $fullResolved.StartsWith($rootResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path '$FullPath' is not under root '$Root'."
    }

    $relative = $fullResolved.Substring($rootResolved.Length).TrimStart('\\')
    return $relative
}

function Load-Config {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Config file not found: $Path"
    }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Get-ExcludedDirMatch {
    param(
        [Parameter(Mandatory = $true)][string]$FullName,
        [Parameter(Mandatory = $true)][string[]]$ExcludedNames
    )
    foreach ($name in $ExcludedNames) {
        if ($FullName -match [Regex]::Escape("\$name\") -or $FullName.EndsWith("\$name") -or $FullName -like "*\$name\*") {
            return $true
        }
    }
    return $false
}

function Invoke-Inventory {
    param(
        [Parameter(Mandatory = $true)]$Config,
        [switch]$IncludeHashes
    )

    $sourceRoot = [System.IO.Path]::GetFullPath($Config.source_root)
    $outputRoot = [System.IO.Path]::GetFullPath($Config.output_root)
    $reportName = $Config.default_report_name
    $excludedDirs = @($Config.exclude_dirs)

    if (-not (Test-Path -LiteralPath $sourceRoot)) {
        throw "Source root not found: $sourceRoot"
    }

    Ensure-Directory -Path $outputRoot
    $runStamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $runFolder = Join-Path $outputRoot "run_$runStamp"
    Ensure-Directory -Path $runFolder

    $script:LogPath = Join-Path $runFolder "inventory.log"
    New-Item -ItemType File -Path $script:LogPath -Force | Out-Null

    Write-Log "Inventory started. Source root: $sourceRoot"
    Write-Log "Output folder: $runFolder"
    Write-Log "Hashes enabled: $($IncludeHashes.IsPresent)"

    $files = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object { -not (Get-ExcludedDirMatch -FullName $_.FullName -ExcludedNames $excludedDirs) }

    $totalFiles = 0
    $inventory = New-Object System.Collections.Generic.List[object]

    foreach ($file in $files) {
        $totalFiles++
        if (($totalFiles % 5000) -eq 0) {
            Write-Log "Processed $totalFiles files..."
        }

        $relativePath = Get-SafeRelativePath -Root $sourceRoot -FullPath $file.FullName
        $extension = if ([string]::IsNullOrWhiteSpace($file.Extension)) { '[no_extension]' } else { $file.Extension.ToLowerInvariant() }
        $hash = $null

        if ($IncludeHashes) {
            try {
                $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
            } catch {
                $hash = '[hash_failed]'
            }
        }

        $inventory.Add([pscustomobject]@{
            RelativePath      = $relativePath
            FullPath          = $file.FullName
            FileName          = $file.Name
            Extension         = $extension
            Directory         = $file.DirectoryName
            SizeBytes         = [int64]$file.Length
            SizeMB            = [math]::Round($file.Length / 1MB, 4)
            LastWriteTime     = $file.LastWriteTime.ToString('s')
            CreatedTime       = $file.CreationTime.ToString('s')
            Attributes        = $file.Attributes.ToString()
            SHA256            = $hash
        })
    }

    $csvPath  = Join-Path $runFolder "$reportName.csv"
    $jsonPath = Join-Path $runFolder "$reportName.json"
    $mdPath   = Join-Path $runFolder "$reportName.md"

    $inventory | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8
    $inventory | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

    $extSummary = $inventory |
        Group-Object -Property Extension |
        Sort-Object -Property Count -Descending |
        ForEach-Object {
            [pscustomobject]@{
                Extension = $_.Name
                FileCount = $_.Count
                TotalBytes = ($_.Group | Measure-Object -Property SizeBytes -Sum).Sum
                TotalGB = [math]::Round((($_.Group | Measure-Object -Property SizeBytes -Sum).Sum) / 1GB, 4)
            }
        }

    $largest = $inventory | Sort-Object -Property SizeBytes -Descending | Select-Object -First 100

    $mdLines = New-Object System.Collections.Generic.List[string]
    $mdLines.Add("# HyperSpin Inventory Report")
    $mdLines.Add("")
    $mdLines.Add("- Source root: `$sourceRoot`")
    $mdLines.Add("- Run folder: `$runFolder`")
    $mdLines.Add("- Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    $mdLines.Add("- Total files: $totalFiles")
    $mdLines.Add("- Hashes enabled: $($IncludeHashes.IsPresent)")
    $mdLines.Add("")
    $mdLines.Add("## Top extensions")
    $mdLines.Add("")
    $mdLines.Add("| Extension | Count | Total GB |")
    $mdLines.Add("|---|---:|---:|")
    foreach ($row in ($extSummary | Select-Object -First 100)) {
        $mdLines.Add("| $($row.Extension) | $($row.FileCount) | $($row.TotalGB) |")
    }
    $mdLines.Add("")
    $mdLines.Add("## Largest files (top 100)")
    $mdLines.Add("")
    $mdLines.Add("| File | Extension | Size GB | Relative Path |")
    $mdLines.Add("|---|---|---:|---|")
    foreach ($row in $largest) {
        $sizeGb = [math]::Round($row.SizeBytes / 1GB, 4)
        $safePath = $row.RelativePath.Replace('|','/')
        $mdLines.Add("| $($row.FileName) | $($row.Extension) | $sizeGb | $safePath |")
    }

    Set-Content -LiteralPath $mdPath -Value $mdLines -Encoding UTF8

    $summaryCsv = Join-Path $runFolder "extension_summary.csv"
    $extSummary | Export-Csv -LiteralPath $summaryCsv -NoTypeInformation -Encoding UTF8

    Write-Log "Inventory complete. Total files: $totalFiles"
    Write-Log "CSV report: $csvPath"
    Write-Log "JSON report: $jsonPath"
    Write-Log "Markdown report: $mdPath"
    Write-Log "Extension summary CSV: $summaryCsv"
}

function Invoke-MirrorRecovery {
    param(
        [Parameter(Mandatory = $true)]$Config,
        [switch]$DryRun
    )

    $sourceRoot = [System.IO.Path]::GetFullPath($Config.source_root)
    $outputRoot = [System.IO.Path]::GetFullPath($Config.output_root)
    $recoveryRoot = [System.IO.Path]::GetFullPath($Config.recovery_root)
    $excludedDirs = @($Config.exclude_dirs)

    if (-not (Test-Path -LiteralPath $sourceRoot)) {
        throw "Source root not found: $sourceRoot"
    }

    Ensure-Directory -Path $outputRoot
    Ensure-Directory -Path $recoveryRoot

    $runStamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $runFolder = Join-Path $outputRoot "recovery_$runStamp"
    Ensure-Directory -Path $runFolder
    $script:LogPath = Join-Path $runFolder "recovery.log"
    New-Item -ItemType File -Path $script:LogPath -Force | Out-Null

    Write-Log "Recovery mirror started. Source root: $sourceRoot"
    Write-Log "Recovery root: $recoveryRoot"
    Write-Log "Dry run: $($DryRun.IsPresent)"

    $files = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object { -not (Get-ExcludedDirMatch -FullName $_.FullName -ExcludedNames $excludedDirs) }

    $copyPlan = New-Object System.Collections.Generic.List[object]
    $copied = 0
    $skipped = 0

    foreach ($file in $files) {
        $relativePath = Get-SafeRelativePath -Root $sourceRoot -FullPath $file.FullName
        $destPath = Join-Path $recoveryRoot $relativePath
        $destDir = Split-Path -Path $destPath -Parent
        $action = 'Skip'

        if (-not (Test-Path -LiteralPath $destPath)) {
            $action = 'CopyNew'
        } else {
            $destItem = Get-Item -LiteralPath $destPath -Force
            if ($destItem.Length -ne $file.Length -or $destItem.LastWriteTime -ne $file.LastWriteTime) {
                $action = 'CopyUpdate'
            }
        }

        $copyPlan.Add([pscustomobject]@{
            RelativePath = $relativePath
            SourcePath   = $file.FullName
            Destination  = $destPath
            SizeBytes    = [int64]$file.Length
            LastWriteTime = $file.LastWriteTime.ToString('s')
            Action       = $action
        })

        if ($action -eq 'Skip') {
            $skipped++
            continue
        }

        if ($DryRun) {
            continue
        }

        Ensure-Directory -Path $destDir
        Copy-Item -LiteralPath $file.FullName -Destination $destPath -Force
        (Get-Item -LiteralPath $destPath).LastWriteTime = $file.LastWriteTime
        $copied++
    }

    $planCsv = Join-Path $runFolder "recovery_plan.csv"
    $copyPlan | Export-Csv -LiteralPath $planCsv -NoTypeInformation -Encoding UTF8
    $copyPlan | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $runFolder "recovery_plan.json") -Encoding UTF8

    $summary = @()
    $summary += "# HyperSpin Recovery Mirror Report"
    $summary += ""
    $summary += "- Source root: `$sourceRoot`"
    $summary += "- Recovery root: `$recoveryRoot`"
    $summary += "- Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    $summary += "- Dry run: $($DryRun.IsPresent)"
    $summary += "- Planned actions: $($copyPlan.Count)"
    $summary += "- Copied this run: $copied"
    $summary += "- Skipped unchanged: $skipped"
    $summary += ""
    $summary += "## Action counts"
    $summary += ""
    $summary += "| Action | Count |"
    $summary += "|---|---:|"
    foreach ($group in ($copyPlan | Group-Object Action | Sort-Object Count -Descending)) {
        $summary += "| $($group.Name) | $($group.Count) |"
    }
    Set-Content -LiteralPath (Join-Path $runFolder "recovery_report.md") -Value $summary -Encoding UTF8

    Write-Log "Recovery mirror complete. Copied: $copied. Skipped: $skipped. Dry run: $($DryRun.IsPresent)"
    Write-Log "Recovery plan CSV: $planCsv"
}

$config = Load-Config -Path $ConfigPath

switch ($Mode) {
    'Inventory' { Invoke-Inventory -Config $config -IncludeHashes:$IncludeHashes }
    'MirrorRecovery' { Invoke-MirrorRecovery -Config $config -DryRun:$DryRun }
    default { throw "Unsupported mode: $Mode" }
}
