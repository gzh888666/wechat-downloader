@echo off
chcp 65001 >nul
echo ========================================
echo   WxDown 打包脚本
echo ========================================
echo.
uv run python _pack.py
pause
