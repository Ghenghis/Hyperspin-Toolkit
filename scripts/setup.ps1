# HyperSpin Extreme Toolkit — Setup Script
# Creates virtual environment and installs dependencies

$ErrorActionPreference = 'Stop'
$ToolkitRoot = Split-Path -Parent $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  HyperSpin Extreme Toolkit — Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.\d+") {
            $pythonCmd = $cmd
            Write-Host "[OK] Found $ver" -ForegroundColor Green
            break
        }
    } catch { }
}

if (-not $pythonCmd) {
    Write-Host "[ERROR] Python 3 not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}

# Create virtual environment
$venvPath = Join-Path $ToolkitRoot ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "[INFO] Creating virtual environment..." -ForegroundColor Yellow
    & $pythonCmd -m venv $venvPath
    Write-Host "[OK] Virtual environment created at $venvPath" -ForegroundColor Green
} else {
    Write-Host "[OK] Virtual environment already exists" -ForegroundColor Green
}

# Activate and install
$pipPath = Join-Path $venvPath "Scripts\pip.exe"
$reqPath = Join-Path $ToolkitRoot "requirements.txt"

Write-Host "[INFO] Installing dependencies..." -ForegroundColor Yellow
& $pipPath install --upgrade pip
& $pipPath install -r $reqPath

if ($LASTEXITCODE -eq 0) {
    Write-Host "" 
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  Setup complete!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  To activate the environment:" -ForegroundColor Cyan
    Write-Host "    .venv\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "  Quick start:" -ForegroundColor Cyan
    Write-Host "    python main.py init        # Discover systems" -ForegroundColor White
    Write-Host "    python main.py audit full  # Full audit" -ForegroundColor White
    Write-Host "    python main.py dashboard   # Web UI" -ForegroundColor White
    Write-Host "    python main.py ai status   # Check AI" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "[ERROR] Some dependencies failed to install." -ForegroundColor Red
    Write-Host "Check error messages above and install manually." -ForegroundColor Yellow
}
