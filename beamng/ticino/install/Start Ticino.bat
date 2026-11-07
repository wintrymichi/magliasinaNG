@echo off
rem Starts BeamNG.drive in the Ticino map, with the streaming helper beside it (start_ticino.ps1).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_ticino.ps1" %*
if errorlevel 1 pause
