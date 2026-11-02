# F3 (task sessions until "end") checks. Run from AgentDesk_AI\ on your Windows PC:
#   powershell -ExecutionPolicy Bypass -File scripts\check_f3.ps1 [-Full]
# 1. Unit tests: tests\test_f3_task_sessions.py (end phrases, the 2-minute question, "here"/"go back", the outline before a click).
# 2. Outline test on your real screen: draws the amber outline for 1.2 s around a rectangle and checks with a screenshot that it was drawn and then erased.
# -Full also runs the whole backend suite.
param([switch]$Full)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root 'backend')
$py = '.venv\Scripts\python.exe'
$env:PYTHONPATH = '.'
$rows = @()
function Step($name, [scriptblock]$run) { & $run; $c = $LASTEXITCODE; $script:rows += [pscustomobject]@{ Check = $name; Result = $(if ($c -eq 0) { 'PASS' } else { 'FAIL' }) } }
Step 'F3 unit tests' { & $py -m pytest tests\test_f3_task_sessions.py -q }
Step 'Outline drawn and erased on the real screen' { & $py scripts\highlight_check.py }
if ($Full) { Step 'Whole backend suite' { & $py -m pytest tests -q } }
$rows | Format-Table -AutoSize
Write-Host @'

BY HAND (assistant running, http://localhost:5173, microphone allowed):
  1. Say "open Downloads". Then WITHOUT pressing anything say "make a folder called Test here" -> approve -> the folder appears in Downloads, the Task card shows Folder: Downloads and the steps with ticks.
  2. Say "go back" -> it opens the parent folder. "what is in here" -> lists it.
  3. Stay silent after a reply: the microphone closes after the follow-up time but the task card stays. After 2 minutes it asks "Shall I end this task?". Say "yes" (ends) or "no" (carries on). Stay silent after the question -> it ends by itself after about 12 s.
  4. Say "that's all" / "end task" / "bas" at any moment -> "Task ended. Anything else?".
  5. In Calculator: "click seven" -> an amber outline appears around the 7 key for about a third of a second, then it is pressed.
  6. Interrupt the assistant while it speaks: it should stop within about 300 ms (NOT measured by me: needs a microphone).
'@
if ($rows | Where-Object Result -eq 'FAIL') { exit 1 }
