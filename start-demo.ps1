# Starts McLender on this PC with sample data (no Fineract, no Docker needed).
# Right-click > "Run with PowerShell", or in a PowerShell window:  .\start-demo.ps1
# Needs Python 3.12+ (python.org) and Node.js 22+ (nodejs.org). Stop it by closing the two windows it opens.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Fail($msg) {
    Write-Host $msg -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

function Need($cmd, $what, $url) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "$what is not installed. Install it from $url, then run this script again." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }
}
Need python "Python 3.12 or newer" "https://www.python.org/downloads/ (tick 'Add python.exe to PATH')"
Need npm "Node.js 22 or newer" "https://nodejs.org/"

$pyVersion = (& python -c "import sys;print('%d.%d' % sys.version_info[:2])")
if ([version]$pyVersion -lt [version]"3.12") {
    Write-Host "Python $pyVersion found; McLender needs 3.12 or newer." -ForegroundColor Red
    Read-Host "Press Enter to close"; exit 1
}

Write-Host "1/3  Setting up the API (first run takes a minute)..." -ForegroundColor Cyan
Set-Location "$root\api"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the Python environment in api\.venv." }
}
& ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail "Could not update pip. Check your internet connection and run this script again." }
& ".venv\Scripts\python.exe" -m pip install --quiet -e ".[dev]"
if ($LASTEXITCODE -ne 0) { Fail "Could not install the API packages. Check your internet connection and run this script again." }

Write-Host "2/3  Setting up the web app (first run takes a few minutes)..." -ForegroundColor Cyan
Set-Location "$root\web"
if (-not (Test-Path "node_modules")) {
    npm install --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue  # so the next run tries again
        Fail "Could not install the web app packages. Check your internet connection and run this script again."
    }
}

Write-Host "3/3  Starting McLender..." -ForegroundColor Cyan
$api = "Set-Location '$root\api'; `$env:MCL_DEV_SMS_INBOX='true'; Write-Host 'McLender API (sample data). SMS codes appear below. Close this window to stop.' -ForegroundColor Green; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
$web = "Set-Location '$root\web'; Write-Host 'McLender web app. Close this window to stop.' -ForegroundColor Green; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $api
Start-Process powershell -ArgumentList "-NoExit", "-Command", $web

Start-Sleep -Seconds 8
Start-Process "http://localhost:5173/staff"
Write-Host ""
Write-Host "McLender is running:" -ForegroundColor Green
Write-Host "  Staff app        http://localhost:5173/staff    sign in: demo / demo   (or officer / officer)"
Write-Host "  Borrower portal  http://localhost:5173/portal   phone: 7012 3344  (code shows in the API window)"
Write-Host "  API docs         http://localhost:8000/docs"
Write-Host ""
Write-Host "Test checklist: docs\TESTING.md. Sample data resets when you close and restart the API window."
Read-Host "Press Enter to close this window (McLender keeps running)"
