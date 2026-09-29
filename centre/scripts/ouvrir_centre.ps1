$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $racine ".venv\Scripts\pythonw.exe"
$python  = Join-Path $racine ".venv\Scripts\python.exe"
$adresse = "http://127.0.0.1:8740"

# Demarre le Centre si besoin, puis l'ouvre dans le navigateur.
& (Join-Path $PSScriptRoot "demarrer_centre.ps1")
if ($LASTEXITCODE -eq 0) { Start-Process $adresse }
