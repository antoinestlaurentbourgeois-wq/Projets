@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-tests.txt
".venv\Scripts\python.exe" -m pytest -q tests
echo.
echo --- Tests du panneau ---
".venv\Scripts\python.exe" -m centre tests-panneau
pause
