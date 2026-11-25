@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 声纹工坊 VoiceClone Studio

if not exist ".venv\Scripts\pythonw.exe" (
    echo [1/2] 首次运行，正在创建虚拟环境...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo 未找到可用的 Python，请先安装 Python 3.10-3.13 并勾选 Add to PATH。
        pause
        exit /b 1
    )
    echo [2/2] 正在安装基础依赖，请耐心等待...
    ".venv\Scripts\python.exe" -m pip install -U pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

start "" ".venv\Scripts\pythonw.exe" "main.py"
