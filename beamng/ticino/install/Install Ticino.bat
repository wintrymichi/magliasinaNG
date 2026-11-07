@echo off
rem Installs or updates the Ticino map for BeamNG.drive (install_ticino.ps1, README in beamng/ticino).
rem Close BeamNG first. Extra options go to the script, e.g.:  "Install Ticino.bat" -ListOnly
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_ticino.ps1" %*
pause
