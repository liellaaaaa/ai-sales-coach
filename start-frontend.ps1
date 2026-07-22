$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontend = Join-Path $root "frontend"
Set-Location $frontend
& "npm.cmd" run dev -- --host 127.0.0.1 --port 5173
