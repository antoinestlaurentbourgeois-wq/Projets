@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sauvegarde.ps1"
type "I:\IA\CENTRE\donnees\taches.log" | more +0
pause
