# Cree le raccourci "Centre de controle" sur le bureau (seul fichier ecrit sur C:).
$racine = Split-Path -Parent $PSScriptRoot
$bureau = [Environment]::GetFolderPath("Desktop")
$lien = Join-Path $bureau "Centre de controle.lnk"
$sh = New-Object -ComObject WScript.Shell
$r = $sh.CreateShortcut($lien)
$r.TargetPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$r.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $PSScriptRoot "ouvrir_centre.ps1") + '"'
$r.WorkingDirectory = $racine
$r.Description = "Ouvre le Centre de controle"
$r.Save()
Write-Host "Raccourci cree : $lien" -ForegroundColor Green
