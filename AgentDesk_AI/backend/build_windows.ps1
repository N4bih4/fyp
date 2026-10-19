# Build the AgentDesk AI backend into a single Windows .exe.
# RUN ONLY AFTER the app is verified working:
#   .venv\Scripts\python scripts\verify_windows.py --api   (all checks green)
# Requires: backend venv active, PyInstaller installed.
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot
.\.venv\Scripts\Activate.ps1

Write-Host "Installing PyInstaller..." -ForegroundColor Cyan
pip install pyinstaller

Write-Host "Building AgentDeskAI.exe (this takes a few minutes)..." -ForegroundColor Cyan
pyinstaller agentdesk.spec --noconfirm

Write-Host ""
Write-Host "Done: dist\AgentDeskAI.exe" -ForegroundColor Green
Write-Host "Run it, then open the frontend (npm run dev) and point it at http://localhost:8000."
Write-Host "Remember: copy your backend .env next to the exe or set the env vars system-wide."
