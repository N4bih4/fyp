@echo off
rem Runs the installer for this process only; no system-wide PowerShell policy change is made.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 (
  echo.
  echo Installation did not finish. See the message above.
  pause
  exit /b 1
)
pause
