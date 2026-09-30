# Arrete le serveur du Centre (et lui seul).
$procs = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*-m centre*' -and $_.CommandLine -like '*\.venv\*' }
if (-not $procs) { Write-Host "Le Centre n'est pas lance."; exit 0 }
foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force }
Write-Host "Le Centre est arrete."
