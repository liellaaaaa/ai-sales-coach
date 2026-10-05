$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Start-Process powershell.exe -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $root "start-backend.ps1")
)

Start-Process powershell.exe -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $root "start-frontend.ps1")
)

Write-Host "Sales Coach MVP is starting..."
Write-Host "Frontend: https://127.0.0.1:5173"
Write-Host "Backend health: http://127.0.0.1:8000/api/health"
Write-Host "Keep the backend and frontend windows open."
Write-Host ""
Write-Host "NOTE: Frontend uses HTTPS (self-signed cert)."
Write-Host "  - On PC: open https://127.0.0.1:5173 and accept the cert warning"
Write-Host "  - On phone: open https://<your-LAN-IP>:5173 and accept the cert warning"
