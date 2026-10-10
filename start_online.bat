@echo off
title AdFreeShono - Personal Music Server (Cloudflare Online Mode)
color 0b

echo ======================================================================
echo           ADFREESHONO - ONLINE MUSIC STREAMING SERVER
echo ======================================================================
echo.
echo [1/2] Starting backend server on http://127.0.0.1:8000...
start /b "" "%~dp0.venv\Scripts\python.exe" run.py

timeout /t 2 /nobreak >nul

echo [2/2] Connecting Cloudflare Tunnel to the internet...
echo.
echo ======================================================================
echo  Look below for the line that says:
echo  https://something.trycloudflare.com
echo.
echo  Share that https link with your friends to listen from their phones!
echo  Press Ctrl+C to stop the server anytime.
echo ======================================================================
echo.

"%~dp0tools\cloudflared.exe" tunnel --url http://127.0.0.1:8000
pause
