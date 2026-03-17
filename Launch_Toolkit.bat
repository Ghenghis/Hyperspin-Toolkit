@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   HyperSpin Extreme Toolkit v2.0
echo   Full Ecosystem Management
echo ============================================================
echo.
echo  1. Initialize (discover systems + emulators)
echo  2. Full Ecosystem Audit
echo  3. Launch Web Dashboard
echo  4. Show Collection Statistics
echo  5. Check AI Provider Status
echo  6. Create Full Backup
echo  7. Show Update History
echo  8. List Available Agents
echo  9. Legacy Inventory (PowerShell)
echo  0. Exit
echo ============================================================
set /p CHOICE=Choose 0-9: 

if "%CHOICE%"=="1" goto init
if "%CHOICE%"=="2" goto audit
if "%CHOICE%"=="3" goto dashboard
if "%CHOICE%"=="4" goto stats
if "%CHOICE%"=="5" goto ai_status
if "%CHOICE%"=="6" goto backup
if "%CHOICE%"=="7" goto update_history
if "%CHOICE%"=="8" goto agents
if "%CHOICE%"=="9" goto legacy
if "%CHOICE%"=="0" goto end

echo Invalid choice.
pause
goto end

:init
python main.py init
pause
goto end

:audit
python main.py audit full
pause
goto end

:dashboard
echo Starting web dashboard at http://127.0.0.1:8888
python main.py dashboard
pause
goto end

:stats
python main.py stats
pause
goto end

:ai_status
python main.py ai status
pause
goto end

:backup
python main.py backup create "D:\Arcade" --label full_backup --type full
pause
goto end

:update_history
python main.py update history
pause
goto end

:agents
python main.py agent list
pause
goto end

:legacy
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0HyperSpinInventory.ps1" -ConfigPath "%~dp0config.json" -Mode Inventory
pause
goto end

:end
endlocal
