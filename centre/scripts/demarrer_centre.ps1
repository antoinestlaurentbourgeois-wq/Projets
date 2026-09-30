$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $racine ".venv\Scripts\pythonw.exe"
$python  = Join-Path $racine ".venv\Scripts\python.exe"
$adresse = "http://127.0.0.1:8740"

# Demarre le serveur sans fenetre, par WMI (il survit ainsi a ce script).
# Ne fait rien si le serveur repond deja.

function Serveur-Repond {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri "$adresse/api/verrou" -TimeoutSec 2; return ($r.StatusCode -eq 200) }
    catch { return $false }
}

if (Serveur-Repond) { Write-Host "Le Centre tourne deja."; exit 0 }
if (-not (Test-Path $pythonw)) { Write-Host "Le Centre n'est pas installe : lancez installer.bat." -ForegroundColor Red; exit 1 }

$commande = '"' + $pythonw + '" -m centre'
$res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $commande; CurrentDirectory = $racine }
if ($res.ReturnValue -ne 0) { Write-Host "Demarrage impossible (code WMI $($res.ReturnValue))." -ForegroundColor Red; exit 1 }

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Serveur-Repond) { Write-Host "Le Centre est demarre."; exit 0 }
}
Write-Host "Le serveur ne repond pas apres 30 secondes. Voyez I:\IA\CENTRE\donnees\centre.log" -ForegroundColor Red
exit 1
