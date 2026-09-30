@echo off
rem Lance le serveur DANS cette fenetre (utile pour voir les erreurs). Ctrl+C pour arreter.
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m centre
pause
