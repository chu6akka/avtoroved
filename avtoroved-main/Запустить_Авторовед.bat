@echo off
cd /d "%~dp0"
echo Starting Avtoroved...
where python >nul 2>nul
if %errorlevel%==0 (
    python app2.py
) else (
    py app2.py
)
if errorlevel 1 (
    echo.
    echo [Error] App did not start. Check Python install / dependencies.
    pause
)
