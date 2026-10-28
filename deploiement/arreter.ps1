#Requires -RunAsAdministrator
# Arrête le serveur et Caddy (par exemple avant une restauration ou une mise à jour).
Stop-ScheduledTask -TaskName "Presence - Serveur" -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "Presence - HTTPS (Caddy)" -ErrorAction SilentlyContinue
Get-Process caddy -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "Application arrêtée. Pour redémarrer : .\demarrer.ps1 (ou redémarrez Windows)."
