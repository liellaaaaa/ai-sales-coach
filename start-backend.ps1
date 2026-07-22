$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$db = (Join-Path $env:TEMP "sales_coach_runtime.db") -replace "\\", "/"
$env:SALES_COACH_DATABASE_URL = "sqlite:///$db"
Set-Location $backend
$envFile = Join-Path $backend ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
    $name, $value = $line.Split("=", 2)
    if ($name.StartsWith("SALES_COACH_") -and $name -ne "SALES_COACH_DATABASE_URL") {
      [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
  }
}
& ".\.venv\Scripts\python.exe" -m app.seed
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
