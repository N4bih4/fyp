# F2 (local intent model) checks. Run from AgentDesk_AI\ on your Windows PC:
#   powershell -ExecutionPolicy Bypass -File scripts\check_f2.ps1 [-Train] [-Epochs 5]
# 1. Validates the dataset and runs the F2 unit tests (no model needed).
# 2. If models\intent\intent_int8.onnx exists: evaluates it on the held-out test set (accuracy, per language, per intent, slots, noisy copy,
#    regex-matcher comparison, CPU latency) -> docs\eval\f2_report.json.
# -Train also retrains from scratch first (about 30-40 minutes, uses all CPU cores; do not run other heavy things).
param([switch]$Train, [int]$Epochs = 5)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$be = 'backend\.venv\Scripts\python.exe'
$ml = 'ml\.venv\Scripts\python.exe'
$rows = @()
function Step($name, [scriptblock]$run) { & $run; $c = $LASTEXITCODE; $script:rows += [pscustomobject]@{ Check = $name; Result = $(if ($c -eq 0) { 'PASS' } else { 'FAIL' }) } }
Step 'Dataset validates' { & $be ml\validate_dataset.py }
Step 'F2 unit tests'     { Push-Location backend; & .venv\Scripts\python.exe -m pytest tests\test_f2_dataset.py -q; Pop-Location }
if ($Train) { Step 'Retrain + export + evaluate' { powershell -ExecutionPolicy Bypass -File ml\retrain.ps1 -Epochs $Epochs } }
elseif ((Test-Path 'models\intent\intent_int8.onnx') -and (Test-Path $ml)) { Step 'Evaluate the exported model' { & $ml ml\evaluate.py } }
else { Write-Host 'No model yet (models\intent). Run with -Train to build it.' }
$rows | Format-Table -AutoSize
Write-Host 'BY HAND (from backend\, with PYTHONPATH=.): .venv\Scripts\python -c "from app.nlu.local_model import get_model; m=get_model(); print(m.predict(''youtube pe atif aslam ka gana chala do''))"'
Write-Host 'Evidence: docs\eval\f2_report.json'
if ($rows | Where-Object Result -eq 'FAIL') { exit 1 }
