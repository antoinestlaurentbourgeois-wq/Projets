' Lance un script PowerShell sans aucune fenetre. Usage : wscript cache.vbs "chemin\script.ps1"
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -File """ & WScript.Arguments(0) & """", 0, False
