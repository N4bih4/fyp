# Agent X AI / AgentDesk AI - Windows installer.
# Creates a private Python 3.12 virtual environment inside this folder and installs the pinned
# dependencies. It does not change system settings, the registry, PATH, Wi-Fi or Bluetooth,
# and it does not start the app or contact anything except the Python package index.
param(
    [string]$PythonExe = "",
    [int]$PipTimeout = 180,
    [switch]$SkipPipInstall
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "AgentDesk_AI\backend"
$venv = Join-Path $backend ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
$lock = Join-Path $backend "requirements.lock.txt"

function Fail($message) { Write-Host "ERROR: $message" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $lock)) { Fail "requirements.lock.txt not found. Run this from the extracted AgentDesk-AI folder." }

# 1. Find Python 3.12 (the only version this release was tested on).
function Test-Python312($exe) {
    try {
        $version = & $exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        return ($LASTEXITCODE -eq 0 -and $version.Trim() -eq "3.12")
    } catch { return $false }
}
$python = $null
if ($PythonExe) {
    if (Test-Python312 $PythonExe) { $python = $PythonExe } else { Fail "$PythonExe is not Python 3.12." }
} else {
    try {
        $candidate = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Python312 $candidate.Trim())) { $python = $candidate.Trim() }
    } catch { }
    if (-not $python) {
        $candidate = Get-Command python -ErrorAction SilentlyContinue
        if ($candidate -and (Test-Python312 $candidate.Source)) { $python = $candidate.Source }
    }
}
if (-not $python) {
    Fail "Python 3.12 was not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run INSTALL.cmd again. Or pass -PythonExe <path>."
}
Write-Host "Using Python: $python"

# 2. Create the virtual environment (kept inside the install folder).
if (Test-Path $venvPython) {
    if (-not (Test-Python312 $venvPython)) { Fail "Existing $venv is not Python 3.12. Delete the .venv folder and run again." }
    Write-Host "Reusing existing virtual environment."
} else {
    Write-Host "Creating virtual environment..."
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) { Fail "Could not create the virtual environment." }
}

# 3. Install pinned dependencies.
if (-not $SkipPipInstall) {
    Write-Host "Installing dependencies (a few minutes on a slow connection)..."
    & $venvPython -m pip install --disable-pip-version-check --retries 10 --timeout $PipTimeout -r $lock
    if ($LASTEXITCODE -ne 0) { Fail "Dependency installation failed. Check your internet connection and run INSTALL.cmd again; it resumes where it stopped." }
}

# 4. Local settings file (no keys are written).
$envFile = Join-Path $backend ".env"
$envExample = Join-Path $root "AgentDesk_AI\.env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host "Created backend\.env from the template. Add GROQ_API_KEY there only if you want cloud AI."
}

# 5. Self-check.
Push-Location $backend
try {
    $env:AGENTDESK_REQUIRE_API_TOKEN = "0"
    & $venvPython -c "import fastapi, uvicorn, sqlalchemy, pydantic, httpx, groq, openai, PIL, pyautogui, pycaw, screen_brightness_control, winsdk; from app.main import app; print('Self-check passed: all modules import.')"
    if ($LASTEXITCODE -ne 0) { Fail "Self-check failed: a dependency did not import. See the error above." }
} finally {
    Remove-Item Env:\AGENTDESK_REQUIRE_API_TOKEN -ErrorAction SilentlyContinue
    Pop-Location
}

Write-Host ""
Write-Host "Installed. Start the app with START_AGENT_X.cmd, then open http://127.0.0.1:8000/" -ForegroundColor Green
Write-Host "Browser tab controls need the extension: see AgentDesk_AI\docs\BROWSER_CONTROLS.md"
exit 0
