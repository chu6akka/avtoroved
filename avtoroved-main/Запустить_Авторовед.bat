@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запуск: Автороведческий анализатор (экспертный протокол)...
where python >nul 2>nul
if %errorlevel%==0 (
    python main.py
) else (
    py main.py
)
if errorlevel 1 (
    echo.
    echo [Ошибка] Программа не запустилась. Проверьте установку Python и зависимостей:
    echo    pip install -r requirements.txt
    pause
)
