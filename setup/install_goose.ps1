<#
.SYNOPSIS
    HyperSpin Agentic Stack Installer — Goose v1.27.2 + all MCP bridges.

.DESCRIPTION
    Downloads Goose CLI v1.27.2 from GitHub, installs it, verifies the
    full stack (hyperspin_toolkit, cli_anything, nemoclaw_agents, openhands),
    and runs the E2E validation.

.USAGE
    .\setup\install_goose.ps1
    .\setup\install_goose.ps1 -SkipGoose       # skip Goose download, just validate
    .\setup\install_goose.ps1 -SkipValidation   # install only, no E2E test
    .\setup\install_goose.ps1 -Force            # re-download even if already installed
#>
param(
    [switch]$SkipGoose,
    [switch]$SkipValidation,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

# ── Config ────────────────────────────────────────────────────────────
$GooseVersion    = "v1.27.2"
$GooseGitHubOrg  = "block"
$GooseGitHubRepo = "goose"
$GooseAsset      = "goose-x86_64-pc-windows-msvc.zip"
$GooseReleaseURL = "https://github.com/$GooseGitHubOrg/$GooseGitHubRepo/releases/download/$GooseVersion/$GooseAsset"

$InstallDir      = "$env:LOCALAPPDATA\Goose\bin"
$ToolkitDir      = "D:\hyperspin_toolkit"
$EnginesDir      = "$ToolkitDir\engines"
$SetupDir        = "$ToolkitDir\setup"
$TempDir         = "$env:TEMP\goose_install"
$SkillsDir       = "$env:APPDATA\Block\goose\config\skills"

# ── Colors ────────────────────────────────────────────────────────────
function Write-OK    { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "  [XX] $msg" -ForegroundColor Red }
function Write-Info  { param($msg) Write-Host "  --> $msg" -ForegroundColor Cyan }
function Write-Hdr   { param($msg) Write-Host "`n=== $msg ===" -ForegroundColor White }

# ── Banner ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  HyperSpin Extreme Toolkit — Agentic Stack Installer" -ForegroundColor Cyan
Write-Host "  Goose $GooseVersion + OpenHands + CLI-Anything + NemoClaw" -ForegroundColor Cyan
Write-Host "  Provider: LM Studio (local, RTX 3090 Ti)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Python check ──────────────────────────────────────────────
Write-Hdr "Step 1: Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    $pyver = & python --version 2>&1
    Write-OK "Python: $pyver"
} else {
    Write-Fail "Python not found — install Python 3.10+ from https://python.org"
    Write-Fail "Aborting."
    exit 1
}

# ── Step 2: pip dependencies ──────────────────────────────────────────
Write-Hdr "Step 2: Python Dependencies"
$packages = @("httpx", "click", "rich", "requests")
foreach ($pkg in $packages) {
    $check = & python -c "import $pkg; print('ok')" 2>&1
    if ($check -eq "ok") {
        Write-OK "$pkg"
    } else {
        Write-Info "Installing $pkg..."
        & python -m pip install $pkg --quiet
        $check2 = & python -c "import $pkg; print('ok')" 2>&1
        if ($check2 -eq "ok") {
            Write-OK "$pkg installed"
        } else {
            Write-Warn "$pkg install failed — some features may not work"
        }
    }
}

# ── Step 3: Goose CLI ─────────────────────────────────────────────────
Write-Hdr "Step 3: Goose CLI $GooseVersion"

$gooseExe = Join-Path $InstallDir "goose.exe"
$gooseOnPath = Get-Command goose -ErrorAction SilentlyContinue

if ($gooseOnPath -and -not $Force) {
    $existing = & goose --version 2>&1
    Write-OK "Goose already installed: $existing"
    Write-Info "Use -Force to re-download."
} elseif ($SkipGoose) {
    Write-Warn "Skipping Goose download (-SkipGoose flag set)"
} else {
    # Download
    Write-Info "Downloading Goose $GooseVersion from GitHub..."
    Write-Info "URL: $GooseReleaseURL"

    if (-not (Test-Path $TempDir)) {
        New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    }
    $zipPath = Join-Path $TempDir $GooseAsset

    try {
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -Uri $GooseReleaseURL -OutFile $zipPath -UseBasicParsing
        Write-OK "Downloaded: $zipPath"
    } catch {
        Write-Fail "Download failed: $($_.Exception.Message)"
        Write-Info "Manual download: $GooseReleaseURL"
        Write-Info "Extract to: $InstallDir"
        Write-Info "Continuing with rest of setup..."
    }

    # Extract
    if (Test-Path $zipPath) {
        Write-Info "Extracting to $InstallDir..."
        if (-not (Test-Path $InstallDir)) {
            New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        }
        try {
            Expand-Archive -Path $zipPath -DestinationPath $InstallDir -Force
            Write-OK "Extracted to $InstallDir"
        } catch {
            Write-Fail "Extraction failed: $($_.Exception.Message)"
        }
        Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
    }

    # Add to PATH if not already there
    $currentPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -notlike "*$InstallDir*") {
        Write-Info "Adding $InstallDir to user PATH..."
        [System.Environment]::SetEnvironmentVariable(
            "Path",
            "$currentPath;$InstallDir",
            "User"
        )
        $env:PATH = "$env:PATH;$InstallDir"
        Write-OK "PATH updated — restart terminal to take effect"
    }

    # Verify
    $gooseExeCheck = Get-Command goose -ErrorAction SilentlyContinue
    if ($gooseExeCheck) {
        $ver = & goose --version 2>&1
        Write-OK "Goose installed: $ver"
    } elseif (Test-Path $gooseExe) {
        Write-OK "Goose binary at: $gooseExe"
        Write-Warn "Not on PATH yet — restart terminal or run: `$env:PATH += ';$InstallDir'"
    } else {
        Write-Warn "Goose binary not found after install — check $InstallDir"
    }
}

# ── Step 4: Verify toolkit engine files ──────────────────────────────
Write-Hdr "Step 4: Toolkit Engine Files"
$engineFiles = @(
    "$ToolkitDir\main.py",
    "$ToolkitDir\mcp_bridge.py",
    "$EnginesDir\cli_anything_bridge.py",
    "$EnginesDir\nemoclaw_agents.py",
    "$EnginesDir\openhands_bridge.py",
    "$EnginesDir\llm_detector.py"
)
$missingEngines = 0
foreach ($f in $engineFiles) {
    if (Test-Path $f) {
        Write-OK (Split-Path $f -Leaf)
    } else {
        Write-Fail "$f — MISSING"
        $missingEngines++
    }
}
if ($missingEngines -gt 0) {
    Write-Warn "$missingEngines engine file(s) missing — re-run toolkit setup"
}

# ── Step 5: Verify Goose skill files ─────────────────────────────────
Write-Hdr "Step 5: Goose Skill Files"
$skills = @(
    "hyperspin-toolkit",
    "hyperspin-audit",
    "hyperspin-update",
    "hyperspin-optimize",
    "hyperspin-backup",
    "hyperspin-releases",
    "hyperspin-mame",
    "hyperspin-ai",
    "hyperspin-vision",
    "hyperspin-orchestrator",
    "hyperspin-cli-anything"
)
$missingSkills = 0
foreach ($skill in $skills) {
    $skillFile = Join-Path $SkillsDir "$skill\SKILL.md"
    if (Test-Path $skillFile) {
        Write-OK "$skill/SKILL.md"
    } else {
        Write-Fail "$skill/SKILL.md — MISSING"
        $missingSkills++
    }
}
if ($missingSkills -gt 0) {
    Write-Warn "$missingSkills skill(s) missing — run goose_setup.py to generate"
}

# ── Step 6: Verify Goose config.yaml ─────────────────────────────────
Write-Hdr "Step 6: Goose config.yaml"
$gooseCfg = "$env:APPDATA\Block\goose\config\config.yaml"
if (Test-Path $gooseCfg) {
    Write-OK "config.yaml found"
    $cfgContent = Get-Content $gooseCfg -Raw
    $checks = @{
        "hyperspin_toolkit extension" = "hyperspin_toolkit:"
        "cli_anything extension"      = "cli_anything:"
        "nemoclaw_agents extension"   = "nemoclaw_agents:"
        "openhands wired"             = "openhands_bridge.py"
        "provider = lmstudio"         = "GOOSE_PROVIDER: lmstudio"
        "model = Devstral-24B"        = "Devstral-Small-2-24B"
        "context = 131072"            = "GOOSE_CONTEXT_LENGTH: 131072"
    }
    foreach ($name in $checks.Keys) {
        if ($cfgContent -like "*$($checks[$name])*") {
            Write-OK $name
        } else {
            Write-Fail "$name — NOT found in config.yaml"
        }
    }
} else {
    Write-Fail "config.yaml not found: $gooseCfg"
    Write-Info "Goose Desktop App may not be installed or config not yet created"
}

# ── Step 7: LM Studio check ───────────────────────────────────────────
Write-Hdr "Step 7: LM Studio API"
try {
    $lmsResp = Invoke-RestMethod -Uri "http://localhost:1234/v1/models" `
        -Headers @{Authorization="Bearer lm-studio"} -TimeoutSec 3
    $modelCount = ($lmsResp.data | Measure-Object).Count
    Write-OK "LM Studio running — $modelCount model(s) loaded"
    if ($lmsResp.data) {
        foreach ($m in $lmsResp.data | Select-Object -First 3) {
            Write-Info "  Model: $($m.id)"
        }
    }
} catch {
    Write-Warn "LM Studio not running at http://localhost:1234"
    Write-Info "Start LM Studio, load a model, and enable the API server"
    Write-Info "Then reload Goose to activate the hyperspin_toolkit extension"
}

# ── Step 8: LM Studio context check ──────────────────────────────────
Write-Hdr "Step 8: LM Studio Context Length"
$lmsSettings = "$env:USERPROFILE\.lmstudio\settings.json"
if (Test-Path $lmsSettings) {
    try {
        $settings = Get-Content $lmsSettings -Raw | ConvertFrom-Json
        $ctxVal = $settings.defaultContextLength.value
        if ($ctxVal -ge 131072) {
            Write-OK "defaultContextLength = $ctxVal ($([math]::Round($ctxVal/1024))K)"
        } else {
            Write-Fail "defaultContextLength = $ctxVal — too low (need 131072+)"
            Write-Info "Auto-fixing..."
            $settings.defaultContextLength = [PSCustomObject]@{type="custom"; value=131072}
            $settings | ConvertTo-Json -Depth 20 | Set-Content $lmsSettings -Encoding UTF8
            Write-OK "Fixed: defaultContextLength = 131072 (128K)"
        }
    } catch {
        Write-Warn "Could not read settings.json: $($_.Exception.Message)"
    }
} else {
    Write-Warn "LM Studio settings.json not found"
}

# ── Step 9: Ollama check ──────────────────────────────────────────────
Write-Hdr "Step 9: Ollama (fallback LLM)"
try {
    $ollamaResp = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3
    $ollamaModels = ($ollamaResp.models | Measure-Object).Count
    Write-OK "Ollama running — $ollamaModels model(s)"
} catch {
    Write-Info "Ollama not running (optional fallback — install from https://ollama.com)"
}

# ── Step 10: E2E MCP Bridge Smoke Test ───────────────────────────────
if (-not $SkipValidation) {
    Write-Hdr "Step 10: E2E MCP Bridge Smoke Tests"
    $bridges = @(
        @{ Name="hyperspin_toolkit (mcp_bridge.py)";  Script="$ToolkitDir\mcp_bridge.py" },
        @{ Name="cli_anything (cli_anything_bridge)"; Script="$EnginesDir\cli_anything_bridge.py" },
        @{ Name="nemoclaw_agents";                    Script="$EnginesDir\nemoclaw_agents.py" },
        @{ Name="openhands_bridge";                   Script="$EnginesDir\openhands_bridge.py" }
    )

    $initPayload = '{"method":"initialize","id":1,"jsonrpc":"2.0","params":{"protocolVersion":"2024-11-05","capabilities":{}}}'
    $listPayload = '{"method":"tools/list","id":2,"jsonrpc":"2.0"}'

    foreach ($bridge in $bridges) {
        if (-not (Test-Path $bridge.Script)) {
            Write-Fail "$($bridge.Name) — script not found"
            continue
        }
        try {
            $proc = Start-Process -FilePath python -ArgumentList $bridge.Script `
                -RedirectStandardInput "$TempDir\init.tmp" `
                -RedirectStandardOutput "$TempDir\out.tmp" `
                -RedirectStandardError "$TempDir\err.tmp" `
                -NoNewWindow -PassThru

            # Write payloads
            "$initPayload`n$listPayload`n" | Set-Content "$TempDir\init.tmp" -Encoding UTF8 -NoNewline
            
            # Give it 8 seconds
            $proc.WaitForExit(8000) | Out-Null

            if (Test-Path "$TempDir\out.tmp") {
                $output = Get-Content "$TempDir\out.tmp" -Raw
                if ($output -like "*tools*") {
                    Write-OK "$($bridge.Name) — responds to tools/list"
                } else {
                    Write-Warn "$($bridge.Name) — started but no tool list returned"
                }
            } else {
                Write-Warn "$($bridge.Name) — no output captured"
            }
        } catch {
            Write-Warn "$($bridge.Name) — test skipped: $($_.Exception.Message)"
        }
    }

    # Cleanup temp files
    Remove-Item "$TempDir\*.tmp" -Force -ErrorAction SilentlyContinue
}

# ── Final Summary ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Setup Complete" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "  1. Start LM Studio → load Devstral-Small-2-24B or Qwen3.5" -ForegroundColor White
Write-Host "  2. Enable LM Studio API server (port 1234)" -ForegroundColor White
Write-Host "  3. Open Goose Desktop → Settings → Provider: LM Studio" -ForegroundColor White
Write-Host "     Model: lmstudio-community/.../Devstral-Small-2-24B-...Q4_K_M.gguf" -ForegroundColor White
Write-Host "  4. Verify extensions are active in Goose → Extensions tab" -ForegroundColor White
Write-Host "     ✓ hyperspin_toolkit   ✓ cli_anything" -ForegroundColor Green
Write-Host "     ✓ nemoclaw_agents     ✓ openhands_bridge" -ForegroundColor Green
Write-Host "  5. Run validation: python D:\hyperspin_toolkit\setup\goose_setup.py --e2e" -ForegroundColor White
Write-Host ""
Write-Host "  Try it: Open Goose and say:" -ForegroundColor Yellow
Write-Host "    'Audit my MAME collection and tell me what needs fixing'" -ForegroundColor Yellow
Write-Host "    'Check all emulator updates and plan a safe batch upgrade'" -ForegroundColor Yellow
Write-Host "    'How much disk space can I safely recover?'" -ForegroundColor Yellow
Write-Host ""

if (Test-Path $TempDir) {
    Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
}
