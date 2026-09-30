foreach ($nom in @("Centre-Gardien", "Centre-Sauvegarde")) {
    if (Get-ScheduledTask -TaskName $nom -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $nom -Confirm:$false; Write-Host "Tache supprimee : $nom" }
    else { Write-Host "Tache absente : $nom" }
}
