$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $racine ".venv\Scripts\pythonw.exe"
$python  = Join-Path $racine ".venv\Scripts\python.exe"
$adresse = "http://127.0.0.1:8740"

# Verifications automatiques sur VOTRE PC : le serveur repond, le verrou est en place, rien n'est accessible sans session.
$ok = $true
function Test($nom, $condition) {
    if ($condition) { Write-Host "[OK]     $nom" -ForegroundColor Green } else { Write-Host "[ECHEC]  $nom" -ForegroundColor Red; $script:ok = $false }
}
function Code($chemin) {
    try { (Invoke-WebRequest -UseBasicParsing -Uri "$adresse$chemin" -MaximumRedirection 0 -TimeoutSec 5).StatusCode }
    catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 } }
}
Test "Le serveur repond (/api/verrou)" ((Code "/api/verrou") -eq 200)
Test "/api/etat refuse sans session (401)" ((Code "/api/etat") -eq 401)
Test "/api/journal refuse sans session (401)" ((Code "/api/journal") -eq 401)
Test "La page d'accueil renvoie vers la connexion (303)" ((Code "/") -eq 303)
$ecoute = Get-NetTCPConnection -LocalPort 8740 -State Listen -ErrorAction SilentlyContinue
Test "Le port 8740 n'ecoute que sur 127.0.0.1" ($ecoute -and -not ($ecoute | Where-Object { $_.LocalAddress -ne "127.0.0.1" }))
if ($ok) { Write-Host "`nTout est bon." -ForegroundColor Green } else { Write-Host "`nAu moins un test a echoue : notez lesquels et transmettez-les." -ForegroundColor Yellow }
