$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
Set-Location $backend
# 数据库连接由 backend/.env 的 SALES_COACH_DATABASE_URL 决定（PostgreSQL / Docker）
& ".\.venv\Scripts\python.exe" -m app.seed
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
