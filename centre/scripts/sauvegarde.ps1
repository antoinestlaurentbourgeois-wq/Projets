$racine = Split-Path -Parent $PSScriptRoot
$python = Join-Path $racine ".venv\Scripts\python.exe"
$journal = "I:\IA\CENTRE\donnees\taches.log"
function Noter($texte) {
    try { Add-Content -Path $journal -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $texte) -Encoding UTF8 } catch { }
}

# Sauvegarde de nuit : archive sans secrets dans I:\IA\CENTRE\sauvegardes (les 7 dernieres sont gardees).
Push-Location $racine
try { $sortie = & $python -m centre sauvegarde 2>&1 | Out-String; Noter ("sauvegarde : " + $sortie.Trim().Replace("`r`n", " | ")) }
catch { Noter ("sauvegarde en erreur : " + $_.Exception.Message) }
Pop-Location
