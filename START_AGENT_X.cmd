@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0AgentDesk_AI\launch.py" %*
) else if exist "%~dp0AgentDesk_AI\.venv\Scripts\python.exe" (
  "%~dp0AgentDesk_AI\.venv\Scripts\python.exe" "%~dp0AgentDesk_AI\launch.py" %*
) else (
  echo Python environment nahi mila. Project setup check karein.
  pause
  exit /b 1
)
if errorlevel 1 pause
