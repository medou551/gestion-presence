#Requires -RunAsAdministrator
<#
  Mise à jour : copiez d'abord les nouveaux fichiers du projet par-dessus l'ancien dossier
  (sans écraser .env, db.sqlite3, media, sauvegardes, venv, deploiement\caddy_data), puis lancez ce script.
#>
$ErrorActionPreference = "Stop"
$Racine = Split-Path -Parent $PSScriptRoot
Set-Location $Racine
$Py = Join-Path $Racine "venv\Scripts\python.exe"
& "$PSScriptRoot\arreter.ps1"
Write-Host "Sauvegarde avant mise à jour..."
& $Py manage.py sauvegarder
& $Py -m pip install -r requirements.txt --quiet
& $Py manage.py initialiser --sans-admin
if ($LASTEXITCODE -ne 0) { throw "Mise à jour de la base impossible : la sauvegarde ci-dessus permet de revenir en arrière." }
& $Py manage.py compacter_base
& "$PSScriptRoot\demarrer.ps1"
& $Py manage.py verifier_base
& $Py manage.py verifier_securite
