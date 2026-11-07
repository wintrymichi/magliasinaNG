@echo off
rem Ticino streaming helper: start it before BeamNG (or while the game is in the menu) and leave the window open.
rem ticino_helper.exe if it is here (built by .github/workflows/ticino_helper.yml), else Python 3 with numpy.
cd /d "%~dp0"
if exist ticino_helper.exe (
  ticino_helper.exe %*
) else (
  py -3 ticino_helper.py %*
)
if errorlevel 1 pause
