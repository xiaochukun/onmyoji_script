@echo off
setlocal

:: 设置资源目录（从参数传入）
set RES_DIR=%1
if "%RES_DIR%"=="" (
    set RES_DIR=yuling
)

:: 清理上次构建
rd /s /q dist
rd /s /q build
del /q main.spec

:: 打包命令
pyinstaller --onefile --collect-all cv2 --add-data "%RES_DIR%;%RES_DIR%" main.py

echo.
echo ✅ 打包完成，文件在 dist 目录下
pause
