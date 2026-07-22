@echo off
setlocal
set "ROOT=%~dp0"

start "sales-coach-backend" cmd /k call "%ROOT%start-backend.cmd"

start "sales-coach-frontend" cmd /k call "%ROOT%start-frontend.cmd"

echo AI 销售陪练 MVP 正在启动...
echo 前端地址: http://127.0.0.1:5173
echo 后端健康检查: http://127.0.0.1:8000/api/health
echo.
echo 请保持弹出的 backend 和 frontend 窗口不要关闭。
pause
