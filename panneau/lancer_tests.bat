@echo off
rem Double-cliquez sur ce fichier pour lancer les tests automatiques (simulation).
cd /d "%~dp0"
"I:\Python\Python312\python.exe" -m unittest discover -s tests -v
echo.
pause
