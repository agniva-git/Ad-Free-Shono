@echo off
title AdFreeShono Server
color 0a
"%~dp0.venv\Scripts\python.exe" "%~dp0run.py"
if %ERRORLEVEL% neq 0 pause
