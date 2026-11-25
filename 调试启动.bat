@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 声纹工坊 - 调试模式（显示控制台输出）

if not exist ".venv\Scripts\python.exe" (
    echo 请先双击「启动.bat」完成环境安装。
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "main.py"
pause
