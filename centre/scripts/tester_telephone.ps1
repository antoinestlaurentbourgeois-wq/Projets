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

# Verifie l'exposition du Centre : joignable par Tailscale, JAMAIS par Internet, et rien sans session.
$ok = $true
function Test($nom, $condition, $aide) {
    if ($condition) { Write-Host "[OK]     $nom" -ForegroundColor Green }
    else { Write-Host "[ECHEC]  $nom" -ForegroundColor Red; if ($aide) { Write-Host "         -> $aide" }; $script:ok = $false }
}
$etat = Etat-Tailscale
$dns = ([string]$etat.Self.DNSName).TrimEnd(".").ToLower()
Test "Tailscale est connecte" ($etat.BackendState -eq "Running") "Ouvrez Tailscale et connectez-vous."
$serve = (& $ts serve status 2>&1 | Out-String)
Test "Tailscale Serve publie 127.0.0.1:8740 (et seulement ca)" (($serve -match "8740") -and -not ($serve -match "Funnel on")) "Lancez tailscale_configurer.bat."
$funnel = (& $ts funnel status 2>&1 | Out-String)
Test "Aucun funnel actif (rien d'expose sur Internet)" (-not ($funnel -match "Funnel on") -and -not ($serve -match "Funnel on") -and -not ($serve -match "\(Funnel")) "Coupez-le : tailscale funnel reset"
$ecoute = Get-NetTCPConnection -LocalPort 8740 -State Listen -ErrorAction SilentlyContinue
Test "Le port 8740 n'ecoute que sur 127.0.0.1" ($ecoute -and -not ($ecoute | Where-Object { $_.LocalAddress -ne "127.0.0.1" })) "Ne changez jamais l'adresse d'ecoute."
function Code($url) { try { (Invoke-WebRequest -UseBasicParsing -Uri $url -MaximumRedirection 0 -TimeoutSec 8).StatusCode } catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 } } }
Test "https://$dns/api/verrou repond (200)" ((Code "https://$dns/api/verrou") -eq 200) "Le Centre tourne-t-il ? HTTPS est-il active dans Tailscale ?"
Test "https://$dns/api/etat refuse sans session (401)" ((Code "https://$dns/api/etat") -eq 401)
Test "https://$dns/api/journal refuse sans session (401)" ((Code "https://$dns/api/journal") -eq 401)
# Simule une requete arrivee SANS l'identite Tailscale (comme le ferait un funnel) : elle doit etre refusee (403).
$curl = (Get-Command curl.exe -ErrorAction SilentlyContinue)
if ($curl) {
    $c = (& curl.exe -s -o NUL -w "%{http_code}" -H "Host: $dns" "http://127.0.0.1:8740/api/verrou")
    Test "Une requete sans identite Tailscale est refusee (403)" ($c -eq "403") "Verifiez reglages.json : exiger_identite_tailscale doit etre vrai."
    $c2 = (& curl.exe -s -o NUL -w "%{http_code}" -H "Host: $dns" -H "Tailscale-User-Login: intrus@example.com" "http://127.0.0.1:8740/api/verrou")
    Test "Un autre compte Tailscale est refuse (403)" ($c2 -eq "403") "Verifiez utilisateurs_tailscale dans reglages.json."
}
Write-Host ""
if ($ok) { Write-Host "Tout est bon : le Centre n'est joignable que par votre reseau Tailscale." -ForegroundColor Green }
else { Write-Host "Au moins un test a echoue : notez lesquels et transmettez-les (ne laissez pas l'acces telephone active)." -ForegroundColor Yellow }
