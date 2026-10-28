# Build the AgentDesk AI Windows exe (one-folder) with PyInstaller.
# Prerequisites: the backend virtual environment from INSTALL.cmd (or `pip install -r requirements.lock.txt`)
# and the web UI built once:  cd ..\frontend ; npm.cmd ci ; npm.cmd run build
# Output: <OutDir>\AgentDeskAI\AgentDeskAI.exe  (serves the API and the web UI on 127.0.0.1:8000)
param(
    [string]$OutDir = (Join-Path $PSScriptRoot "..\dist-exe")
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Backend .venv not found. Run INSTALL.cmd first." }
if (-not (Test-Path (Join-Path $PSScriptRoot "..\frontend\dist\index.html"))) { throw "Build the web UI first (frontend: npm.cmd run build)." }

Write-Host "Installing PyInstaller into the backend venv..." -ForegroundColor Cyan
& $python -m pip install --disable-pip-version-check pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Could not install PyInstaller." }

$work = Join-Path $env:TEMP "agentdesk_pyinstaller_work"
Write-Host "Building (a few minutes)..." -ForegroundColor Cyan
& $python -m PyInstaller agentdesk.spec --noconfirm --distpath $OutDir --workpath $work
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host ""
Write-Host "Done: $OutDir\AgentDeskAI\AgentDeskAI.exe" -ForegroundColor Green
Write-Host "Copy the whole AgentDeskAI folder. The database and an optional .env live next to the exe."
Write-Host "The exe is unsigned: Windows SmartScreen / antivirus may warn on first run."
