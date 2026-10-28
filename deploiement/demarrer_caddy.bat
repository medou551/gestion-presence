@echo off
rem Lance Caddy (HTTPS). Appele par la tache planifiee "Presence - HTTPS (Caddy)".
rem Les certificats et l'autorite locale sont conserves dans deploiement\caddy_data.
cd /d "%~dp0"
set XDG_DATA_HOME=%~dp0caddy_data
set XDG_CONFIG_HOME=%~dp0caddy_config
if not exist journaux mkdir journaux
"%~dp0caddy.exe" run --config "%~dp0Caddyfile" --adapter caddyfile >> "%~dp0journaux\caddy_console.log" 2>&1
