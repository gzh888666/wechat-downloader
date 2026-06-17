@echo off
chcp 65001 >nul
echo ========================================
echo   WxDown Build Script
echo ========================================
echo.
"%~dp0.venv\Scripts\python.exe" "%~dp0_pack.py"
if errorlevel 1 (
    echo.
    echo Build failed! Check error messages above.
)
pause
