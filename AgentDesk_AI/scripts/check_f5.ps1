# F5 (device control) checks. Run from AgentDesk_AI\ on your Windows PC:
#   powershell -ExecutionPolicy Bypass -File scripts\check_f5.ps1 [-NoLive]
# 1. tests\test_f5_device.py (fake OS). 2. LIVE on this PC: scripts\device_live.py - battery, Do Not Disturb, keep awake, a 600 s shutdown that it cancels at once,
#    File Explorer sort / view / hidden files / properties / search in a temp folder, Night light on then back. Windows appear for a few seconds: do not touch the
#    mouse. It never locks, sleeps, restarts, shuts down or changes the radios. Everything is put back.
param([switch]$NoLive)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root 'backend')
$env:PYTHONPATH = '.'
$rows = @()
function Step($name, [scriptblock]$run) { & $run; $c = $LASTEXITCODE; $script:rows += [pscustomobject]@{ Check = $name; Result = $(if ($c -eq 0) { 'PASS' } else { 'FAIL' }) } }
Step 'F5 unit tests' { & .venv\Scripts\python.exe -m pytest tests\test_f5_device.py -q }
if (-not $NoLive) { Step 'Live device checks (>= 90% to pass)' { & .venv\Scripts\python.exe scripts\device_live.py } }
$rows | Format-Table -AutoSize
Write-Host @'

BY HAND (these are deliberately NOT automated):
  1. "lock my pc" -> Approve -> the lock screen appears. Unlock with Windows Hello / PIN; after 20+ seconds locked the assistant says "welcome back".
  2. "unlock my pc" -> it explains that no app can unlock Windows.
  3. "shut down the pc" -> Approve -> it says "Shutting down in 10 seconds. Say cancel to stop it." Say "cancel": nothing shuts down. (Or run shutdown /a.)
  4. "put the laptop to sleep" -> the PC sleeps (it is reported as accepted, not verified: nothing can read a sleeping PC).
  5. "turn on airplane mode" -> Wi-Fi and Bluetooth go off (so the assistant's cloud calls stop); "airplane mode off" restores exactly what was on.
Evidence: docs\eval\f5_live.json
'@
if ($rows | Where-Object Result -eq 'FAIL') { exit 1 }
