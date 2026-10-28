@echo off
rem ============================================================
rem  Gestion de presence - installation et lancement sur CE PC
rem  (essai ou petite installation sans reseau).
rem  Double-cliquez ce fichier. Pour le bureau en HTTPS, utilisez
rem  deploiement\installer.ps1 (voir DEPLOIEMENT.md).
rem ============================================================
cd /d "%~dp0"
title Gestion de presence

set "PYLANCE="
where py >nul 2>nul && set "PYLANCE=py"
if not defined PYLANCE where python >nul 2>nul && set "PYLANCE=python"
if not defined PYLANCE (
  echo Python est introuvable.
  echo Installez-le depuis https://www.python.org/downloads/
  echo en cochant "Add python.exe to PATH", puis relancez ce fichier.
  pause
  exit /b 1
)

if not exist "venv\Scripts\python.exe" (
  echo Creation de l'environnement Python...
  %PYLANCE% -m venv venv || goto erreur
)
echo Installation des dependances...
"venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
"venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet || goto erreur

"venv\Scripts\python.exe" manage.py initialiser || goto erreur

echo.
"venv\Scripts\python.exe" serveur.py
goto fin

:erreur
echo.
echo Une erreur est survenue. Lisez le message ci-dessus.
pause
exit /b 1

:fin
pause
