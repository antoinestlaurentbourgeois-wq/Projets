@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tailscale_arreter.ps1"
pause
