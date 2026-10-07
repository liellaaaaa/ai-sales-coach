@echo off
setlocal
cd /d "%~dp0backend"
".venv\Scripts\python.exe" -m app.seed
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
