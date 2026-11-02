# U7 (vision fallback) checks. Run from AgentDesk_AI\ on your Windows PC:
#   powershell -ExecutionPolicy Bypass -File scripts\check_u7.ps1 [-NoLive] [-Full]
# 1. Unit tests on a fake screen, fake OCR and fake model: tests\test_u7_vision.py.
# 2. LIVE: scripts\vision_live.py opens its own Tk app (UI Automation sees nothing inside it), runs 20 steps through screen_act with the real
#    screen, Windows OCR and the Groq vision model, and checks each step against the app's own state file. About 3-4 minutes: do NOT touch the
#    mouse or keyboard. It sends window pictures of that test app only to your Groq key. -NoLive skips it. -Full runs the whole suite too.
param([switch]$NoLive, [switch]$Full)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$py = @('.venv\Scripts\python.exe', '.venv-p3\Scripts\python.exe') | ForEach-Object { Join-Path $backend $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $py) { Write-Error 'No backend venv found (backend\.venv)'; exit 1 }
$out = Join-Path $root ("docs\eval\u7_" + (Get-Date -Format 'yyyy-MM-dd_HHmm'))
New-Item -ItemType Directory -Force $out | Out-Null
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = $backend
$rows = @()
function Step($name, [scriptblock]$run, $log) {
  & $run *> (Join-Path $out $log)
  $code = $LASTEXITCODE
  $script:rows += [pscustomobject]@{ Check = $name; Result = $(if ($code -eq 0) { 'PASS' } else { 'FAIL' }); Log = $log }
}
Push-Location $backend
Step 'U7 unit tests (fake screen)' { & $py -m pytest tests\test_u7_vision.py -q } 'pytest_u7.txt'
if (-not $NoLive) { Step 'Live 20 steps on a UIA-blind app (>= 90% to pass)' { & $py scripts\vision_live.py --pause 3 --keep-images (Join-Path $out 'images') --out (Join-Path $out 'u7_live.json') } 'live.txt' }
if ($Full) { Step 'Whole backend test suite' { & $py -m pytest tests -q } 'pytest_all.txt' }
Pop-Location
$rows | Format-Table -AutoSize | Tee-Object -FilePath (Join-Path $out 'SUMMARY.txt')
if (-not $NoLive) { Get-Content (Join-Path $out 'live.txt') | Where-Object { $_ -match '^\[|^\{|UI Automation' } }
Write-Host @"

BY HAND (assistant running, http://localhost:5173):
  1. Open a game or an app with custom-drawn buttons (not Chrome, Notepad or Office). Say 'click Play in <app>' -> the assistant says it needs to look at the screen, then clicks.
  2. 'What does the screen say?' -> reads from the screenshot, no approval.
  3. Turn cloud answers OFF in Settings, repeat -> refused, no picture sent.
  4. Say 'click Delete' on a window with a Delete button -> HIGH risk, needs Approve.
Evidence: $out
"@
if ($rows | Where-Object Result -eq 'FAIL') { exit 1 }
