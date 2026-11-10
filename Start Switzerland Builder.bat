@echo off
rem switzerlandNG (Switzerland Builder): double-click to start. The first start installs the app's own Python (5-10
rem minutes), then the app opens in the browser. Keep this window open while you use it; closing it stops the app.
rem The whole script is one block: cmd reads a block at once, so an update that rewrites this file while it runs
rem cannot make cmd read the rest of a different file (cmd reads a .bat line by line at byte offsets).
(
  title switzerlandNG
  cd /d "%~dp0"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0beamng\builder\launch\start.ps1" %*
  if errorlevel 1 if not defined SWISSBUILDER_NO_PAUSE pause
  exit /b
)
