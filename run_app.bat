@echo off
echo Dang khoi dong Codeinvest...
.\venv\Scripts\python.exe AICcode.py
if %errorlevel% neq 0 (
    echo.
    echo [LOI] Ung dung da dung lai bat thuong.
    pause
)
