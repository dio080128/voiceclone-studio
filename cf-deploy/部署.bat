@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   声纹工坊 · 部署到 Cloudflare
echo ============================================
echo.
echo 项目: restless-math-a985
echo 作用: 更新网站页面 + 启用下载加速
echo.
echo 第一次运行会:
echo   1. 自动下载 wrangler 工具（约 30 MB）
echo   2. 打开浏览器让你登录 Cloudflare，点 Allow 授权
echo   3. 自动上传并部署
echo.
echo 全程约 2-3 分钟。以后改完再双击这个文件就会重新部署。
echo.
pause

echo.
echo [部署中] 请稍候...
echo.

call npx --yes wrangler@latest deploy

if errorlevel 1 (
    echo.
    echo ============================================
    echo   部署失败
    echo ============================================
    echo.
    echo 常见原因:
    echo   1. 还没登录 -- 重新双击本文件，在浏览器里点 Allow
    echo   2. 网络问题 -- 多试一次
    echo   3. 没有 Node.js -- 去 https://nodejs.org 装一个 LTS 版
    echo.
) else (
    echo.
    echo ============================================
    echo   部署成功
    echo ============================================
    echo.
    echo 现在验证:
    echo   https://mctuesday.top/about        网站页面
    echo   https://dl.mctuesday.top/models.zip  下载加速
    echo.
)

pause
