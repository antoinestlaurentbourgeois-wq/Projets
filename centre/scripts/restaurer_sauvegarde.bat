@echo off
rem Usage : restaurer_sauvegarde.bat centre-AAAAMMJJ-HHMMSS.zip I:\IA\CENTRE\restauration
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m centre restaurer %1 %2
pause
