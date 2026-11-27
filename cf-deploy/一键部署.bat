@echo off
chcp 936 >nul
cd /d "%~dp0"
title 声纹工坊 - 部署到 Cloudflare

where node >nul 2>nul
if errorlevel 1 (
    echo [错误] 没找到 Node.js，请先装 LTS 版：https://nodejs.org
    pause
    exit /b 1
)

echo ============================================
echo   声纹工坊 - 一键部署到 Cloudflare
echo   项目: restless-math-a985
echo ============================================
echo.
echo [1/2] 正在部署，首次会先下载 wrangler，约 1-2 分钟...
echo.
call npx --yes wrangler@latest deploy

if errorlevel 1 (
    echo.
    echo 部署没成功，可能还没登录 Cloudflare。
    echo 接下来会打开浏览器，点 Allow 授权，之后自动重新部署。
    echo.
    pause
    call npx --yes wrangler@latest login
    if errorlevel 1 (
        echo [错误] 登录失败，检查网络后重试。
        pause
        exit /b 1
    )
    echo.
    echo 重新部署...
    call npx --yes wrangler@latest deploy
    if errorlevel 1 (
        echo [错误] 部署仍然失败，把上面的报错发我。
        pause
        exit /b 1
    )
)

echo.
echo [2/2] 验证下载链接...
echo.
curl.exe -sI https://dl.mctuesday.top/voiceclone-studio-v1.0.1-setup.exe | findstr /i "HTTP content-length"

echo.
echo ============================================
echo   完成，打开看看：
echo   下载页  https://mctuesday.top/download
echo ============================================
pause
