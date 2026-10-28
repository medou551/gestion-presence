#Requires -RunAsAdministrator
<#
  Arrête l'application et retire les tâches planifiées et la règle de pare-feu.
  Les données (base, photos chiffrées, sauvegardes, .env) ne sont PAS supprimées.
#>
$ErrorActionPreference = "Continue"
foreach ($t in @("Presence - Serveur", "Presence - HTTPS (Caddy)", "Presence - Sauvegarde")) {
    Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Tâche retirée : $t"
}
Get-NetFirewallRule -DisplayName "Gestion de présence (HTTPS)" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Host "Règle de pare-feu retirée."
Get-Process caddy -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "Terminé. Vos données sont toujours dans le dossier du projet."
