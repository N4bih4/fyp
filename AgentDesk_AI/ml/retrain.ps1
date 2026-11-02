# Rebuild, validate, train, export and evaluate the local intent model. Run from AgentDesk_AI\ :
#   powershell -ExecutionPolicy Bypass -File ml\retrain.ps1 [-Corrections] [-Epochs 5] [-SkipTrain]
# -Corrections adds the corrections you made in the app (asks for your consent by passing --i-consent: only use it if you agree).
# About 30-40 minutes on a 12-core CPU (training); no GPU needed.
param([switch]$Corrections, [int]$Epochs = 5, [switch]$SkipTrain)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$be = 'backend\.venv\Scripts\python.exe'
$ml = 'ml\.venv\Scripts\python.exe'
if (-not (Test-Path $ml)) {
  Write-Host 'Creating ml\.venv (downloads torch CPU, transformers, onnxruntime: about 1 GB)...'
  python -m venv ml\.venv
  & $ml -m pip install -r ml\requirements-train.txt
}
if ($Corrections) { & $be ml\collect_corrections.py --i-consent }
& $be ml\build_dataset.py
& $be ml\validate_dataset.py
if ($LASTEXITCODE -ne 0) { Write-Error 'The dataset has errors: fix them first.'; exit 1 }
if (-not $SkipTrain) {
  & $ml ml\train.py --epochs $Epochs
  & $ml ml\export_onnx.py
}
& $ml ml\evaluate.py
