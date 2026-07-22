@echo off
setlocal
cd /d "%~dp0backend"
set "SALES_COACH_DATABASE_URL=sqlite:///%TEMP:\=/%/sales_coach_runtime.db"
".venv\Scripts\python.exe" -m app.seed
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
