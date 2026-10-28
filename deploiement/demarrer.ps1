#Requires -RunAsAdministrator
# Démarre le serveur et Caddy.
Start-ScheduledTask -TaskName "Presence - Serveur"
Start-ScheduledTask -TaskName "Presence - HTTPS (Caddy)"
Write-Host "Application démarrée."
