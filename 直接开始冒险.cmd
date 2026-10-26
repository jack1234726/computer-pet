@echo off
set "PET_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if not exist "%PET_PYTHON%" (
 echo Python runtime not found.
 pause
 exit /b 1
)
start "" "%PET_PYTHON%" "%~dp0launch.py" adventure_game.py
