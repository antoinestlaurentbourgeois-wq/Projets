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

# Coupe l'acces telephone : retire la publication Tailscale Serve du Centre (le Centre reste utilisable sur le PC).
& $ts serve --https=443 off
if ($LASTEXITCODE -ne 0) { Write-Host "Essai avec 'serve reset'..." -ForegroundColor Yellow; & $ts serve reset }
& $ts serve status
Write-Host "Acces telephone coupe." -ForegroundColor Green
