@echo off
setlocal
cd /d "%~dp0"
rem Desktop app: native panel, always-on-top orb and tray icon. Add --minimized to start with only the orb.
set "PY=%~dp0AgentDesk_AI\backend\.venv\Scripts\pythonw.exe"
if not exist "%PY%" set "PY=%~dp0AgentDesk_AI\backend\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Python environment nahi mila. Pehle INSTALL.cmd chalayein.
  pause
  exit /b 1
)
"%PY%" -c "import webview, pystray" 2>nul || (
  echo Desktop shell ke packages missing hain. Ye command chalayein:
  echo   AgentDesk_AI\backend\.venv\Scripts\python.exe -m pip install -r AgentDesk_AI\backend\requirements-desktop.txt
  pause
  exit /b 1
)
start "" "%PY%" "%~dp0AgentDesk_AI\desktop\shell.py" %*
