@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check pytest httpx
".venv\Scripts\python.exe" -m pytest -q tests
cd /d "%~dp0..\..\panneau" 2>nul && "%~dp0..\.venv\Scripts\python.exe" -m unittest discover -s tests
pause
