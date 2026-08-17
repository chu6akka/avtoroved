@echo off
rem ASCII only: cmd.exe reads .bat in OEM codepage, non-ASCII breaks parsing.
cd /d "%~dp0"
echo Starting Avtoroved (expert protocol)...
where python >nul 2>nul
if %errorlevel%==0 (
    python main.py
) else (
    py main.py
)
if errorlevel 1 (
    echo.
    echo [Error] App did not start. Install dependencies:
    echo     pip install -r requirements.txt
    pause
)
