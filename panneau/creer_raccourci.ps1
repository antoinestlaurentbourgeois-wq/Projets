# Crée le raccourci « Panneau IA locale » sur le bureau.
# Ne demande pas de droits administrateur. N'installe rien.

$ErrorActionPreference = 'Stop'
$dossier = $PSScriptRoot
$pythonw = 'I:\Python\Python312\pythonw.exe'
$script  = Join-Path $dossier 'panneau.pyw'

if (-not (Test-Path $pythonw)) {
    Write-Host "pythonw.exe introuvable : $pythonw" -ForegroundColor Red
    Write-Host "Corrigez la ligne `$pythonw dans creer_raccourci.ps1."
    exit 1
}
if (-not (Test-Path $script)) {
    Write-Host "panneau.pyw introuvable dans $dossier" -ForegroundColor Red
    exit 1
}

# Le dossier Bureau réel (fonctionne aussi s'il est dans OneDrive).
$bureau = [Environment]::GetFolderPath('Desktop')
$chemin = Join-Path $bureau 'Panneau IA locale.lnk'

$wsh = New-Object -ComObject WScript.Shell
$raccourci = $wsh.CreateShortcut($chemin)
$raccourci.TargetPath       = $pythonw
$raccourci.Arguments        = '"' + $script + '"'
$raccourci.WorkingDirectory = $dossier
$raccourci.IconLocation     = "$pythonw,0"
$raccourci.Description      = 'Allumer / éteindre Docker, Open WebUI, Kokoro, LM Studio et Crew'
$raccourci.Save()

Write-Host "Raccourci créé : $chemin" -ForegroundColor Green
