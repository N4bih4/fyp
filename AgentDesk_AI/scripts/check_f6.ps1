# F6 (work documents) checks. Run from AgentDesk_AI\ on your Windows PC:
#   powershell -ExecutionPolicy Bypass -File scripts\check_f6.ps1 [-Live] [-RealSearch]
# 1. tests\test_f6_documents.py (fake search / pages / AI). 2. -Live: the real fetcher, the real Groq key and the real writers (Word, Markdown, PDF via Edge) into a TEMP
#    folder (your Documents is not touched; nothing is opened). About 2 minutes, about 30 AI calls on the small model. -RealSearch uses Wikipedia / Tavily (needs
#    WIKIPEDIA_CONTACT_EMAIL or a Tavily key in backend\.env).
param([switch]$Live, [switch]$RealSearch)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root 'backend')
$env:PYTHONPATH = '.'
$rows = @()
function Step($name, [scriptblock]$run) { & $run; $c = $LASTEXITCODE; $script:rows += [pscustomobject]@{ Check = $name; Result = $(if ($c -eq 0) { 'PASS' } else { 'FAIL' }) } }
Step 'F6 unit tests' { & .venv\Scripts\python.exe -m pytest tests\test_f6_documents.py -q }
if ($Live) {
  $flags = @('--out', '../docs/eval/f6_live.json', '--keep', '../docs/eval/f6_samples'); if ($RealSearch) { $flags += '--real-search' }
  Step 'Live documents (>= 85% to pass)' { & .venv\Scripts\python.exe scripts\document_live.py @flags }
}
$rows | Format-Table -AutoSize
Write-Host @'

BY HAND (assistant running, cloud answers ON in Settings):
  1. Say "research solar energy and make me a file" -> it asks how detailed and in which language (no approval for the question). Say "brief, in English" -> approve once -> progress
     lines appear (and a Stop button) -> the file opens in Word -> "Your file is ready ...". Check that the headings, text and the Sources list look right.
  2. "make a study plan for my exams" -> same question; then check the label says no outside sources were used.
  3. "summarise the 3 PDFs in Downloads into notes" with three PDFs there -> a notes file with one section per topic and the file names as sources.
  4. Press Stop while it writes -> nothing is saved. Turn cloud answers OFF -> it refuses and sends nothing.
  5. Ask for "as PDF" and "in Urdu": open both and look at them (the Urdu PDF layout was not checked by eye).
Evidence: docs\eval\f6_live.json, docs\eval\f6_samples\
'@
if ($rows | Where-Object Result -eq 'FAIL') { exit 1 }
