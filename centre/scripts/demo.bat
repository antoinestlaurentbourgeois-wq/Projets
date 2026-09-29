@echo off
rem Mode demo : PC simule, rien n'est lance pour de vrai. Fermez la fenetre pour arreter.
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m centre demo
pause
