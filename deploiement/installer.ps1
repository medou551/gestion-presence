#Requires -RunAsAdministrator
<#
  Gestion de présence — installation sur un serveur Windows du bureau.

  Ce script, à lancer UNE fois en tant qu'administrateur :
    1. installe l'application (environnement Python, dépendances, base de données) ;
    2. configure le mode production (HTTPS, DEBUG désactivé, adresse du serveur) ;
    3. restreint l'accès au dossier aux administrateurs et au système ;
    4. installe Caddy (HTTPS) et son certificat ;
    5. ouvre le pare-feu (réseau privé uniquement) ;
    6. crée les tâches planifiées : démarrage automatique et sauvegarde chaque soir.

  Utilisation (PowerShell en administrateur) :
    cd C:\GestionPresence\deploiement
    powershell -ExecutionPolicy Bypass -File .\installer.ps1
  ou avec l'adresse du serveur :
    powershell -ExecutionPolicy Bypass -File .\installer.ps1 -Adresse 192.168.1.10
#>
param(
    [string]$Adresse = "",
    [string]$HeureSauvegarde = "21:00"
)
$ErrorActionPreference = "Stop"
$Deploiement = $PSScriptRoot
$Racine = Split-Path -Parent $PSScriptRoot
Set-Location $Racine

function Etape($texte) { Write-Host ""; Write-Host "==> $texte" -ForegroundColor Cyan }
function Ok($texte) { Write-Host "    OK : $texte" -ForegroundColor Green }
function Attention($texte) { Write-Host "    ATTENTION : $texte" -ForegroundColor Yellow }

Write-Host "Gestion de présence — installation dans $Racine" -ForegroundColor White

if ($Racine -like "$env:USERPROFILE*") {
    Attention "Le projet est dans votre dossier personnel. Il est conseillé de le placer dans C:\GestionPresence."
    $rep = Read-Host "Continuer quand même ? (o/n)"
    if ($rep -ne "o") { exit 1 }
}

# ---------------------------------------------------------------- 1. Python
Etape "Vérification de Python"
$PythonLanceur = $null
foreach ($cmd in @("py", "python")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { $PythonLanceur = $cmd; break }
}
if (-not $PythonLanceur) {
    throw "Python est introuvable. Installez-le depuis https://www.python.org/downloads/ (cochez « Add python.exe to PATH »), puis relancez ce script."
}
& $PythonLanceur --version

Etape "Création de l'environnement Python et installation des dépendances"
$Py = Join-Path $Racine "venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { & $PythonLanceur -m venv (Join-Path $Racine "venv") }
& $Py -m pip install --upgrade pip --quiet
& $Py -m pip install -r (Join-Path $Racine "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) { throw "L'installation des dépendances a échoué." }
Ok "Dépendances installées"

# ---------------------------------------------------------------- 2. Configuration
Etape "Adresse du serveur sur le réseau"
if (-not $Adresse) {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.PrefixOrigin -ne "WellKnown" } |
           Select-Object -First 1).IPAddress
    $Adresse = Read-Host "Adresse IP (fixe) de ce serveur sur le réseau [$ip]"
    if (-not $Adresse) { $Adresse = $ip }
}
if (-not $Adresse) { throw "Adresse du serveur inconnue." }
Ok "Adresse : $Adresse (pensez à la rendre fixe dans votre box / routeur)"

Etape "Configuration de production (.env, Caddyfile)"
& $Py manage.py configurer_production --adresse $Adresse
if ($LASTEXITCODE -ne 0) { throw "Configuration impossible." }

Etape "Base de données (sauvegarde préalable, tables, contrôle, administrateur)"
& $Py manage.py initialiser
if ($LASTEXITCODE -ne 0) { throw "L'initialisation de la base a échoué : lisez le message ci-dessus." }
& $Py manage.py compacter_base

# ---------------------------------------------------------------- 3. Droits sur le dossier
Etape "Protection du dossier (administrateurs et système uniquement)"
# SID universels : S-1-5-32-544 = Administrateurs, S-1-5-18 = Système (quel que soit la langue de Windows)
& icacls $Racine /inheritance:r /grant:r "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" /T /C /Q | Out-Null
Ok "Seuls les administrateurs et le système peuvent lire le dossier (.env, base, photos chiffrées, sauvegardes)"

# ---------------------------------------------------------------- 4. Caddy
Etape "Installation de Caddy (HTTPS)"
$Caddy = Join-Path $Deploiement "caddy.exe"
if (-not (Test-Path $Caddy)) {
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri "https://caddyserver.com/api/download?os=windows&arch=amd64" -OutFile $Caddy -UseBasicParsing
        Ok "Caddy téléchargé"
    } catch {
        throw "Téléchargement de Caddy impossible. Téléchargez « caddy_windows_amd64.exe » sur https://github.com/caddyserver/caddy/releases, renommez-le caddy.exe, placez-le dans $Deploiement, puis relancez ce script."
    }
}
& $Caddy version

# ---------------------------------------------------------------- 5. Pare-feu
Etape "Pare-feu : HTTPS autorisé sur le réseau privé uniquement"
Get-NetFirewallRule -DisplayName "Gestion de présence (HTTPS)" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "Gestion de présence (HTTPS)" -Direction Inbound -Protocol TCP -LocalPort 80,443 `
    -Action Allow -Profile Private,Domain | Out-Null
Ok "Ports 80 et 443 ouverts (réseaux privé et domaine). Le port 8000 reste fermé : l'application n'écoute que sur 127.0.0.1."
$profil = (Get-NetConnectionProfile | Select-Object -First 1).NetworkCategory
if ($profil -eq "Public") { Attention "Le réseau de ce PC est en mode « Public » : passez-le en « Privé » dans les paramètres Windows, sinon les autres postes ne pourront pas se connecter." }

# ---------------------------------------------------------------- 6. Tâches planifiées
Etape "Démarrage automatique et sauvegardes"
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$reglages = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$auDemarrage = New-ScheduledTaskTrigger -AtStartup

$serveur = New-ScheduledTaskAction -Execute $Py -Argument "`"$Racine\serveur.py`"" -WorkingDirectory $Racine
Register-ScheduledTask -TaskName "Presence - Serveur" -Action $serveur -Trigger $auDemarrage -Principal $principal -Settings $reglages -Force | Out-Null

$caddyAction = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Deploiement\demarrer_caddy.bat`"" -WorkingDirectory $Deploiement
Register-ScheduledTask -TaskName "Presence - HTTPS (Caddy)" -Action $caddyAction -Trigger $auDemarrage -Principal $principal -Settings $reglages -Force | Out-Null

$reglagesSauv = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$sauvegarde = New-ScheduledTaskAction -Execute $Py -Argument "manage.py sauvegarder" -WorkingDirectory $Racine
$chaqueSoir = New-ScheduledTaskTrigger -Daily -At $HeureSauvegarde
Register-ScheduledTask -TaskName "Presence - Sauvegarde" -Action $sauvegarde -Trigger $chaqueSoir -Principal $principal -Settings $reglagesSauv -Force | Out-Null
Ok "Tâches créées : serveur et HTTPS au démarrage de Windows, sauvegarde chiffrée chaque jour à $HeureSauvegarde"

Stop-ScheduledTask -TaskName "Presence - Serveur" -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "Presence - HTTPS (Caddy)" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName "Presence - Serveur"
Start-ScheduledTask -TaskName "Presence - HTTPS (Caddy)"

# ---------------------------------------------------------------- 7. Certificat
Etape "Certificat HTTPS"
$racineCA = Join-Path $Deploiement "caddy_data\caddy\pki\authorities\local\root.crt"
for ($i = 0; $i -lt 30 -and -not (Test-Path $racineCA); $i++) { Start-Sleep -Seconds 1 }
if (Test-Path $racineCA) {
    Import-Certificate -FilePath $racineCA -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    $aDistribuer = Join-Path $Deploiement "certificat_a_installer_sur_les_postes.crt"
    Copy-Item $racineCA $aDistribuer -Force
    & icacls $aDistribuer /grant "*S-1-5-32-545:R" | Out-Null
    Ok "Certificat installé sur ce serveur."
    Ok "Fichier à installer sur la borne et les autres postes : $aDistribuer"
} else {
    Attention "Le certificat de Caddy n'a pas encore été créé. Consultez $Deploiement\journaux\caddy.log puis relancez ce script."
}

# ---------------------------------------------------------------- 8. Vérification
Etape "Vérification de la sécurité"
Start-Sleep -Seconds 3
& $Py manage.py verifier_securite

Write-Host ""
Write-Host "Installation terminée." -ForegroundColor Green
Write-Host "  Adresse de l'application : https://$Adresse"
Write-Host "  Sur ce serveur          : https://localhost"
Write-Host ""
Write-Host "Prochaines étapes :"
Write-Host "  1. Copiez le fichier $Racine\.env sur une clé USB rangée en lieu sûr (sans lui, les photos et sauvegardes sont illisibles)."
Write-Host "  2. Installez le certificat sur la borne et les postes (voir DEPLOIEMENT.md)."
Write-Host "  3. Connectez-vous en administrateur, créez les services, les employés et les comptes."
