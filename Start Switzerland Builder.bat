@echo off
rem Switzerland Builder: double-click to start. The first start installs the app's own Python (5-10 minutes),
rem then the app opens in the browser. Keep this window open while you use it; closing it stops the app.
title switzerlandNG
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0beamng\builder\launch\start.ps1" %*
set "SB_EXIT=%errorlevel%"
if not "%SB_EXIT%"=="0" if not defined SWISSBUILDER_NO_PAUSE pause
exit /b %SB_EXIT%
