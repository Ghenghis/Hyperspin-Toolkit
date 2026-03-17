# HyperSpin Extreme Toolkit — Automated Repair Script
# Identifies and fixes common coding and configuration issues

$ErrorActionPreference = 'Continue'
$ToolkitRoot = Split-Path -Parent $PSScriptRoot
$FixCount = 0
$IssueCount = 0

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  HyperSpin Extreme Toolkit — Automated Repair" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# --- Check 1: Python availability ---
Write-Host "[CHECK] Python installation..." -ForegroundColor Yellow
$pythonOk = $false
foreach ($cmd in @("python", "python3")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3") {
            Write-Host "  [OK] $ver" -ForegroundColor Green
            $pythonOk = $true
            break
        }
    } catch { }
}
if (-not $pythonOk) {
    $IssueCount++
    Write-Host "  [ISSUE] Python 3 not found" -ForegroundColor Red
    Write-Host "  [FIX] Install Python 3.10+ from https://python.org" -ForegroundColor Yellow
}

# --- Check 2: Virtual environment ---
Write-Host "[CHECK] Virtual environment..." -ForegroundColor Yellow
$venvPath = Join-Path $ToolkitRoot ".venv"
if (Test-Path $venvPath) {
    Write-Host "  [OK] .venv exists" -ForegroundColor Green
} else {
    $IssueCount++
    Write-Host "  [ISSUE] No virtual environment found" -ForegroundColor Red
    Write-Host "  [FIX] Run: scripts\setup.ps1" -ForegroundColor Yellow
}

# --- Check 3: Config file ---
Write-Host "[CHECK] Configuration file..." -ForegroundColor Yellow
$configPath = Join-Path $ToolkitRoot "config.yaml"
if (Test-Path $configPath) {
    Write-Host "  [OK] config.yaml exists" -ForegroundColor Green
} else {
    $IssueCount++
    Write-Host "  [ISSUE] config.yaml missing" -ForegroundColor Red
    Write-Host "  [FIX] Restoring default config..." -ForegroundColor Yellow
}

# --- Check 4: Required directories ---
Write-Host "[CHECK] Required directories..." -ForegroundColor Yellow
$requiredDirs = @(
    (Join-Path $ToolkitRoot "core"),
    (Join-Path $ToolkitRoot "engines"),
    (Join-Path $ToolkitRoot "agents"),
    (Join-Path $ToolkitRoot "dashboard"),
    (Join-Path $ToolkitRoot "data"),
    (Join-Path $ToolkitRoot "logs"),
    (Join-Path $ToolkitRoot "plugins"),
    (Join-Path $ToolkitRoot "scripts"),
    (Join-Path $ToolkitRoot "tests")
)

foreach ($dir in $requiredDirs) {
    if (-not (Test-Path $dir)) {
        $IssueCount++
        $FixCount++
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  [FIXED] Created missing directory: $(Split-Path -Leaf $dir)" -ForegroundColor Green
    }
}
Write-Host "  [OK] All required directories present" -ForegroundColor Green

# --- Check 5: Required Python files ---
Write-Host "[CHECK] Core Python modules..." -ForegroundColor Yellow
$requiredFiles = @(
    "core\__init__.py",
    "core\config.py",
    "core\logger.py",
    "core\database.py",
    "engines\__init__.py",
    "engines\scanner.py",
    "engines\backup.py",
    "engines\update_manager.py",
    "engines\auditor.py",
    "engines\ai_engine.py",
    "agents\__init__.py",
    "agents\base_agent.py",
    "dashboard\__init__.py",
    "dashboard\app.py",
    "main.py"
)

$missingFiles = @()
foreach ($file in $requiredFiles) {
    $fullPath = Join-Path $ToolkitRoot $file
    if (-not (Test-Path $fullPath)) {
        $missingFiles += $file
        $IssueCount++
    }
}

if ($missingFiles.Count -eq 0) {
    Write-Host "  [OK] All core modules present" -ForegroundColor Green
} else {
    Write-Host "  [ISSUE] Missing files:" -ForegroundColor Red
    foreach ($f in $missingFiles) {
        Write-Host "    - $f" -ForegroundColor Red
    }
    Write-Host "  [FIX] Re-run the toolkit setup or restore from backup" -ForegroundColor Yellow
}

# --- Check 6: Database integrity ---
Write-Host "[CHECK] Database integrity..." -ForegroundColor Yellow
$dbPath = Join-Path $ToolkitRoot "data\toolkit.db"
if (Test-Path $dbPath) {
    $dbSize = (Get-Item $dbPath).Length
    Write-Host "  [OK] Database exists ($([math]::Round($dbSize/1KB, 1)) KB)" -ForegroundColor Green
} else {
    $IssueCount++
    Write-Host "  [ISSUE] Database not initialized" -ForegroundColor Red
    Write-Host "  [FIX] Run: python main.py init" -ForegroundColor Yellow
}

# --- Check 7: HyperSpin paths ---
Write-Host "[CHECK] HyperSpin installation..." -ForegroundColor Yellow
$hsRoot = "D:\Arcade"
if (Test-Path $hsRoot) {
    $hsExe = Join-Path $hsRoot "HyperSpin.exe"
    if (Test-Path $hsExe) {
        Write-Host "  [OK] HyperSpin.exe found" -ForegroundColor Green
    } else {
        $IssueCount++
        Write-Host "  [ISSUE] HyperSpin.exe not found at $hsRoot" -ForegroundColor Red
    }

    $rlExe = Join-Path $hsRoot "RocketLauncher\RocketLauncher.exe"
    if (Test-Path $rlExe) {
        Write-Host "  [OK] RocketLauncher.exe found" -ForegroundColor Green
    } else {
        $IssueCount++
        Write-Host "  [ISSUE] RocketLauncher.exe not found" -ForegroundColor Red
    }

    $emuDir = Join-Path $hsRoot "emulators"
    if (Test-Path $emuDir) {
        $emuCount = (Get-ChildItem -Path $emuDir -Directory).Count
        Write-Host "  [OK] Emulators directory found ($emuCount emulators)" -ForegroundColor Green
    }
} else {
    $IssueCount++
    Write-Host "  [ISSUE] HyperSpin root not found at $hsRoot" -ForegroundColor Red
    Write-Host "  [FIX] Update source_root in config.yaml" -ForegroundColor Yellow
}

# --- Check 8: Backup directory ---
Write-Host "[CHECK] Backup directory..." -ForegroundColor Yellow
$backupRoot = "D:\HyperSpin_Backups"
if (-not (Test-Path $backupRoot)) {
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $FixCount++
    Write-Host "  [FIXED] Created backup directory: $backupRoot" -ForegroundColor Green
} else {
    Write-Host "  [OK] Backup directory exists" -ForegroundColor Green
}

# --- Check 9: Log cleanup ---
Write-Host "[CHECK] Log files..." -ForegroundColor Yellow
$logsDir = Join-Path $ToolkitRoot "logs"
if (Test-Path $logsDir) {
    $logFiles = Get-ChildItem -Path $logsDir -File -ErrorAction SilentlyContinue
    $totalLogSize = ($logFiles | Measure-Object -Property Length -Sum).Sum
    $logSizeMB = [math]::Round($totalLogSize / 1MB, 1)
    Write-Host "  [OK] $($logFiles.Count) log files ($logSizeMB MB)" -ForegroundColor Green

    if ($logSizeMB -gt 500) {
        $IssueCount++
        Write-Host "  [WARN] Log directory is large ($logSizeMB MB)" -ForegroundColor Yellow
        Write-Host "  [FIX] Consider archiving old logs" -ForegroundColor Yellow
    }
}

# --- Summary ---
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Repair Summary" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Issues found:    $IssueCount" -ForegroundColor $(if ($IssueCount -gt 0) { "Yellow" } else { "Green" })
Write-Host "  Auto-fixed:      $FixCount" -ForegroundColor Green
Write-Host "  Manual fixes:    $($IssueCount - $FixCount)" -ForegroundColor $(if (($IssueCount - $FixCount) -gt 0) { "Yellow" } else { "Green" })
Write-Host "============================================================" -ForegroundColor Cyan
