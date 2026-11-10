@echo off
rem Updates switzerlandNG to the newest version on GitHub (only the files that changed), then starts it.
rem Your builds, downloads and settings stay. "Update switzerlandNG.bat --check" only says whether one is out,
rem "--full" downloads the whole version again (to repair an install). One block, read at once (see the start file).
(
  title switzerlandNG update
  cd /d "%~dp0"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0beamng\builder\launch\start.ps1" update %*
  if errorlevel 1 if not defined SWISSBUILDER_NO_PAUSE pause
  exit /b
)
