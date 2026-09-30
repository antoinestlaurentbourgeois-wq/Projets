$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $racine ".venv\Scripts\pythonw.exe"
$python  = Join-Path $racine ".venv\Scripts\python.exe"
$adresse = "http://127.0.0.1:8740"

# Installation du Centre de controle : tout reste sur I: (rien sur C:).
# Python 3.12 attendu dans I:\Python\Python312 (deja present chez vous).

if ($racine.Substring(0,2).ToUpper() -eq "C:") {
    Write-Host "ERREUR : le dossier du Centre est sur C:. Copiez-le sur I: (par exemple I:\Python\centre) puis relancez." -ForegroundColor Red
    exit 1
}
$pythonSysteme = "I:\Python\Python312\python.exe"
if (-not (Test-Path $pythonSysteme)) {
    Write-Host "ERREUR : $pythonSysteme est introuvable. Indiquez le bon chemin en editant ce fichier (ligne pythonSysteme)." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $racine "centre\__main__.py"))) {
    Write-Host "ERREUR : le dossier 'centre' est introuvable dans $racine. Copiez bien tout le contenu du dossier centre." -ForegroundColor Red
    exit 1
}

Write-Host "1/4  Creation de l'environnement Python dans $racine\.venv ..."
if (-not (Test-Path $python)) { & $pythonSysteme -m venv (Join-Path $racine ".venv"); if ($LASTEXITCODE -ne 0) { throw "venv a echoue" } }

Write-Host "2/4  Installation de Starlette et uvicorn (les caches restent sur I:) ..."
$env:PIP_CACHE_DIR = Join-Path $racine ".pip-cache"
$env:TEMP = Join-Path $racine ".tmp"; $env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
& $python -m pip install --disable-pip-version-check -r (Join-Path $racine "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip a echoue" }

Write-Host "3/4  Dossier des donnees : I:\IA\CENTRE\donnees ..."
New-Item -ItemType Directory -Force -Path "I:\IA\CENTRE\donnees" | Out-Null

Write-Host "4/4  Verification que le panneau est bien trouve ..."
& $python -c "import sys; sys.path.insert(0, r'$racine'); from centre.config import Config; import os; c = Config(); print('Panneau :', c.dossier_panneau); assert os.path.isfile(os.path.join(c.dossier_panneau, 'panneau_logique.py')), 'panneau introuvable'"
if ($LASTEXITCODE -ne 0) { throw "le panneau est introuvable (variable CENTRE_PANNEAU)" }

Write-Host ""
Write-Host "Installation terminee." -ForegroundColor Green
Write-Host "Etape suivante : double-cliquez sur definir_verrou.bat, puis sur creer_raccourci.bat."
