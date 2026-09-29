$racine = Split-Path -Parent $PSScriptRoot
$python = Join-Path $racine ".venv\Scripts\python.exe"
$journal = "I:\IA\CENTRE\donnees\taches.log"
function Noter($texte) {
    try { Add-Content -Path $journal -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $texte) -Encoding UTF8 } catch { }
}

# Gardien : lance toutes les 10 minutes par le Planificateur de taches.
# 1) le serveur repond-il ? sinon on le relance ;  2) verifications plus fines (python -m centre gardien).
function Serveur-Repond {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8740/api/verrou" -TimeoutSec 4; return ($r.StatusCode -eq 200) } catch { return $false }
}
if (-not (Serveur-Repond)) {
    Noter "Le serveur ne repond pas : relance."
    & (Join-Path $PSScriptRoot "demarrer_centre.ps1") | Out-Null
    Start-Sleep -Seconds 3
    if (Serveur-Repond) { Noter "Serveur relance." } else { Noter "ECHEC de la relance." }
}
Push-Location $racine
try { $sortie = & $python -m centre gardien 2>&1 | Out-String; Noter ("gardien : " + $sortie.Trim().Replace("`r`n", " | ")) }
catch { Noter ("gardien en erreur : " + $_.Exception.Message) }
Pop-Location
