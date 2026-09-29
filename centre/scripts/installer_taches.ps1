# Cree les deux taches planifiees (utilisateur courant, sans droits administrateur) :
#   Centre-Gardien    toutes les 10 minutes
#   Centre-Sauvegarde chaque nuit a 03:00 (rattrapee au demarrage si le PC etait eteint)
$ErrorActionPreference = "Stop"
$vbs = Join-Path $PSScriptRoot "cache.vbs"
$wscript = Join-Path $env:SystemRoot "System32\wscript.exe"

function Argument-Script($nom) { return ('//B "{0}" "{1}"' -f $vbs, (Join-Path $PSScriptRoot $nom)) }

# Gardien
$action = New-ScheduledTaskAction -Execute $wscript -Argument (Argument-Script "gardien.ps1")
$declencheur = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
$reglages = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "Centre-Gardien" -Action $action -Trigger $declencheur -Settings $reglages -Description "Verifie le Centre de controle toutes les 10 minutes" -Force | Out-Null
Write-Host "Tache creee : Centre-Gardien (toutes les 10 minutes)" -ForegroundColor Green

# Sauvegarde de nuit
$action2 = New-ScheduledTaskAction -Execute $wscript -Argument (Argument-Script "sauvegarde.ps1")
$declencheur2 = New-ScheduledTaskTrigger -Daily -At "03:00"
$reglages2 = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "Centre-Sauvegarde" -Action $action2 -Trigger $declencheur2 -Settings $reglages2 -Description "Sauvegarde de nuit du Centre de controle (sans secrets)" -Force | Out-Null
Write-Host "Tache creee : Centre-Sauvegarde (chaque nuit a 03:00)" -ForegroundColor Green
Write-Host ""
Write-Host "Verification : ouvrez le Planificateur de taches Windows (taskschd.msc) > Bibliotheque du Planificateur de taches."
Write-Host "Le journal des taches est dans I:\IA\CENTRE\donnees\taches.log ; la page Journal du Centre affiche l'etat du gardien."
