# AdFreeShono - 1-Click Online Launcher via Cloudflare Tunnel
$Host.UI.RawUI.WindowTitle = "AdFreeShono - Online Music Server"

Write-Host "`n======================================================================" -ForegroundColor Cyan
Write-Host "          ADFREESHONO - ONLINE MUSIC STREAMING SERVER" -ForegroundColor Yellow
Write-Host "======================================================================`n" -ForegroundColor Cyan

# 1. Start Python backend in background
Write-Host "[1/2] Starting backend server on http://127.0.0.1:8000..." -ForegroundColor Green
$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$serverProc = Start-Process -FilePath $pythonExe -ArgumentList "run.py" -WorkingDirectory $PSScriptRoot -PassThru -NoNewWindow

Start-Sleep -Seconds 2

# 2. Start Cloudflare Tunnel
Write-Host "[2/2] Connecting Cloudflare Tunnel to the internet..." -ForegroundColor Green
Write-Host "`n======================================================================" -ForegroundColor Cyan
Write-Host " Look below for your public HTTPS URL (ends in .trycloudflare.com):" -ForegroundColor Yellow
Write-Host " Open that link on your phone and share it with your friends!" -ForegroundColor Yellow
Write-Host " Press Ctrl+C to stop the server anytime." -ForegroundColor White
Write-Host "======================================================================`n" -ForegroundColor Cyan

$cloudflared = Join-Path $PSScriptRoot "tools\cloudflared.exe"

try {
    & $cloudflared tunnel --url http://127.0.0.1:8000
} finally {
    if ($serverProc -and !$serverProc.HasExited) {
        Stop-Process -Id $serverProc.Id -Force -ErrorAction SilentlyContinue
    }
}
