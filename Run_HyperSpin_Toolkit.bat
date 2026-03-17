@echo off
setlocal EnableExtensions
cd /d "%~dp0"

:: ── Locate Python ────────────────────────────────────────────────
where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python was not found in PATH.
  echo Install Python 3.10+ and try again.
  pause
  exit /b 1
)

set "TOOLKIT=%~dp0"
set "MAIN=%TOOLKIT%main.py"

if not exist "%MAIN%" (
  echo ERROR: main.py not found in %TOOLKIT%
  pause
  exit /b 1
)

:: ── Auto-reconcile drives on startup (fingerprint-based) ─────────
echo [*] Reconciling drive index (fingerprint-based auto-detection)...
python "%MAIN%" drives reconcile 2>nul
echo.

:menu
echo ============================================================
echo   HyperSpin Extreme Toolkit
echo ============================================================
echo   DRIVES
echo     1. Scan all drives (fingerprint + arcade detection)
echo     2. Show drive status (roles, fingerprints, disk usage)
echo     3. Full drive index (all known drives incl. offline)
echo     4. Auto-assign drive roles
echo     5. Detect drive types (NVMe / SSD / HDD)
echo   AUDIT
echo     6. System inventory scan
echo     7. ROM audit (CRC32/SHA1 verification)
echo     8. Media audit (missing/corrupt assets)
echo   TOOLS
echo     9. Launch dashboard (web UI)
echo    10. Start MCP bridge (AI agent interface)
echo     0. Exit
echo ============================================================
set /p CHOICE=Choose 0-10: 

if "%CHOICE%"=="1"  goto drives_scan
if "%CHOICE%"=="2"  goto drives_status
if "%CHOICE%"=="3"  goto drives_index
if "%CHOICE%"=="4"  goto drives_auto
if "%CHOICE%"=="5"  goto drives_type
if "%CHOICE%"=="6"  goto inventory
if "%CHOICE%"=="7"  goto rom_audit
if "%CHOICE%"=="8"  goto media_audit
if "%CHOICE%"=="9"  goto dashboard
if "%CHOICE%"=="10" goto mcp
if "%CHOICE%"=="0"  goto end

echo Invalid choice.
pause
goto menu

:drives_scan
python "%MAIN%" drives scan --min-gb 100
pause
goto menu

:drives_status
python "%MAIN%" drives status
pause
goto menu

:drives_index
python "%MAIN%" drives index
pause
goto menu

:drives_auto
python "%MAIN%" drives auto
pause
goto menu

:drives_type
python "%MAIN%" drives detect-type --all-drives
pause
goto menu

:inventory
python "%MAIN%" scan
pause
goto menu

:rom_audit
echo Enter system name (e.g. MAME, or "all"):
set /p SYS_NAME=System: 
python "%MAIN%" audit rom "%SYS_NAME%"
pause
goto menu

:media_audit
echo Enter system name (e.g. MAME, or "all"):
set /p SYS_NAME=System: 
python "%MAIN%" audit media "%SYS_NAME%"
pause
goto menu

:dashboard
echo Starting dashboard on http://localhost:8888 ...
python "%MAIN%" dashboard
pause
goto menu

:mcp
echo Starting MCP bridge (stdio mode)...
python "%TOOLKIT%mcp_bridge.py"
pause
goto menu

:end
endlocal
