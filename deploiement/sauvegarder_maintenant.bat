@echo off
rem Sauvegarde chiffree immediate (base + photos) dans le dossier "sauvegardes".
cd /d "%~dp0.."
"venv\Scripts\python.exe" manage.py sauvegarder
pause
