# F4 (browser extension 2.0 + YouTube) checks. Run from AgentDesk_AI\ on your Windows PC:
#   powershell -ExecutionPolicy Bypass -File scripts\check_f4.ps1 [-Live] [-NoYoutube]
# 1. Extension unit tests (fake DOM) and the Python tests for the bridge, the commands and the native host.
# 2. -Live: starts its OWN backend on port 8000 (stop the assistant first) and a REAL Edge with a temporary profile + the real extension, then runs the
#    commands through the task API: websites on a local test page, YouTube on the real site. About 5-10 minutes; Edge runs hidden. Chrome 137+ ignores
#    --load-extension, so Chrome has to be checked by hand (below).
param([switch]$Live, [switch]$NoYoutube)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = 'backend\.venv\Scripts\python.exe'
$rows = @()
function Step($name, [scriptblock]$run) { & $run; $c = $LASTEXITCODE; $script:rows += [pscustomobject]@{ Check = $name; Result = $(if ($c -eq 0) { 'PASS' } else { 'FAIL' }) } }
foreach ($t in 'test_controls', 'test_pairing', 'test_youtube', 'test_f4_youtube') { Step "extension $t" { node "browser-extension\tests\$t.cjs" } }
Step 'F4 python tests' { Push-Location backend; $env:PYTHONPATH = '.'; & .venv\Scripts\python.exe -m pytest tests\test_f4_browser.py tests\test_u5_browser.py -q; Pop-Location }
if ($Live) {
  Push-Location frontend
  $flags = @('--browser', 'msedge', '--out', '../../docs/eval/f4_live.json'); if ($NoYoutube) { $flags += '--no-youtube' }
  Step 'Live run in a real Edge (>= 95% to pass)' { node e2e\f4_live.mjs @flags }
  Pop-Location
}
$rows | Format-Table -AutoSize
Write-Host @'

BY HAND (Chrome, because automation cannot load an extension into branded Chrome 137+):
  1. chrome://extensions -> Developer mode -> Load unpacked -> the browser-extension folder. Open the app's setup page to pair. The popup must say connected.
  2. powershell -File scripts\diagnose_extension.ps1 -> no PROBLEM lines.
  3. powershell -File scripts\install_native_host.ps1, then press Reconnect now in the popup: the channel must read native. Close the browser for a minute and reopen it: it must reconnect by itself.
  4. Say "play atif aslam songs on youtube" -> the first real result plays (no ad, no Short); "pause", "skip 10 seconds", "speed 1.5", "theatre mode", "turn on captions", "like this video", "what's playing".
  5. With Chrome AND Edge both running the extension: click Edge, give a command; click Chrome, give another. Each must act in the browser you used last.
Evidence: docs\eval\f4_live.json
'@
if ($rows | Where-Object Result -eq 'FAIL') { exit 1 }
