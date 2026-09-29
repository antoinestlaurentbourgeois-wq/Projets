$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
$donnees = "I:\IA\CENTRE\donnees"
$reglages = Join-Path $donnees "reglages.json"

function Trouver-Tailscale {
    $c = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in @("C:\Program Files\Tailscale\tailscale.exe", "C:\Program Files (x86)\Tailscale\tailscale.exe")) { if (Test-Path $p) { return $p } }
    return $null
}
$ts = Trouver-Tailscale
if (-not $ts) {
    Write-Host "ERREUR : tailscale.exe est introuvable. Installez Tailscale (https://tailscale.com/download) et connectez-vous, puis relancez." -ForegroundColor Red
    exit 1
}
function Etat-Tailscale {
    $json = & $ts status --json 2>$null
    if (-not $json) { throw "tailscale status n'a rien renvoye : Tailscale est-il lance et connecte ?" }
    return ($json | ConvertFrom-Json)
}

# Ouvre le Centre a votre telephone, par Tailscale Serve (HTTPS, reseau prive Tailscale uniquement).
# Ce script ne rend RIEN accessible sur Internet : jamais de "funnel".

$etat = Etat-Tailscale
if ($etat.BackendState -ne "Running") { Write-Host "Tailscale n'est pas connecte (etat : $($etat.BackendState)). Ouvrez Tailscale et connectez-vous." -ForegroundColor Red; exit 1 }
$dns = ([string]$etat.Self.DNSName).TrimEnd(".").ToLower()
if (-not $dns) { Write-Host "Aucun nom MagicDNS. Activez MagicDNS et HTTPS dans la console d'administration Tailscale (page DNS)." -ForegroundColor Red; exit 1 }
$id = [string]$etat.Self.UserID
$login = ""
if ($etat.User -and $etat.User.$id) { $login = ([string]$etat.User.$id.LoginName).ToLower() }
Write-Host "Nom de ce PC dans Tailscale : $dns"
Write-Host "Compte Tailscale             : $login"
if (-not $login) { Write-Host "ATTENTION : compte non trouve, l'identite ne sera pas limitee a votre compte." -ForegroundColor Yellow }

# 1) reglages.json : hote autorise + identite Tailscale exigee (on garde les autres reglages)
New-Item -ItemType Directory -Force -Path $donnees | Out-Null
$obj = New-Object PSObject
if (Test-Path $reglages) { try { $obj = Get-Content $reglages -Raw -Encoding UTF8 | ConvertFrom-Json } catch { Write-Host "reglages.json illisible : il sera recree." -ForegroundColor Yellow; $obj = New-Object PSObject } }
function Definir($nom, $valeur) { if ($obj.PSObject.Properties.Name -contains $nom) { $obj.$nom = $valeur } else { $obj | Add-Member -NotePropertyName $nom -NotePropertyValue $valeur } }
$hotes = @(); if ($obj.PSObject.Properties.Name -contains "hotes_autorises") { $hotes = @($obj.hotes_autorises) }
if ($hotes -notcontains $dns) { $hotes += $dns }
Definir "hotes_autorises" $hotes
if ($login) { Definir "utilisateurs_tailscale" @($login) }
Definir "exiger_identite_tailscale" $true
$texte = $obj | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($reglages, $texte, (New-Object System.Text.UTF8Encoding $false))
Write-Host "reglages.json mis a jour."

# 2) redemarrer le Centre pour qu'il relise les reglages
& (Join-Path $PSScriptRoot "arreter_centre.ps1")
& (Join-Path $PSScriptRoot "demarrer_centre.ps1")
if ($LASTEXITCODE -ne 0) { exit 1 }

# 3) Tailscale Serve : HTTPS 443 (reseau Tailscale seulement) -> 127.0.0.1:8740
Write-Host "Configuration de Tailscale Serve..."
& $ts serve --bg --https=443 http://127.0.0.1:8740
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "La commande 'tailscale serve' a echoue. Causes frequentes :" -ForegroundColor Yellow
    Write-Host " - HTTPS n'est pas active pour votre reseau : console d'administration Tailscale > DNS > 'Enable HTTPS'."
    Write-Host " - Ancienne version de Tailscale : mettez a jour, ou essayez a la main : tailscale serve --bg 8740"
    exit 1
}
& $ts serve status
Write-Host ""
Write-Host "Termine. Sur le telephone (Tailscale active), ouvrez :  https://$dns/" -ForegroundColor Green
Write-Host "Puis lancez tester_telephone.bat pour verifier que rien n'est expose sur Internet."
