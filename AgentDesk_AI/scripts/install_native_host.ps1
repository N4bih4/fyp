# Registers the Agent X native messaging host for Chrome and Edge (current user only; no admin needed), or removes it.
#   powershell -ExecutionPolicy Bypass -File scripts\install_native_host.ps1            (install)
#   powershell -ExecutionPolicy Bypass -File scripts\install_native_host.ps1 -Uninstall
# What it does: writes browser-extension\native\com.agentdesk.bridge.json and agentdesk_host.cmd (next to the host script) and adds ONE registry value per
# browser under HKCU\Software\...\NativeMessagingHosts\com.agentdesk.bridge pointing at that JSON file. Uninstall deletes exactly those.
# Why: with it the browser starts a small helper that keeps the extension's background worker alive, so "extension not connected" stops happening after
# the worker sleeps. Without it the extension still works over its own WebSocket (and reconnects by itself).
param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$native = Join-Path $root 'browser-extension\native'
$name = 'com.agentdesk.bridge'
$keys = @("HKCU:\Software\Google\Chrome\NativeMessagingHosts\$name", "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\$name")
if ($Uninstall) {
  foreach ($k in $keys) { if (Test-Path $k) { Remove-Item $k -Force; Write-Host "removed $k" } }
  Remove-Item (Join-Path $native "$name.json"), (Join-Path $native 'agentdesk_host.cmd') -ErrorAction SilentlyContinue
  exit 0
}
$py = @('backend\.venv\Scripts\python.exe', 'backend\.venv-p3\Scripts\python.exe') | ForEach-Object { Join-Path $root $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $py) { Write-Error 'No backend venv found (backend\.venv): it provides the websockets package the host needs.'; exit 1 }
$manifest = Get-Content (Join-Path $root 'browser-extension\manifest.json') -Raw | ConvertFrom-Json
# The extension id is fixed by the "key" in manifest.json: sha256 of the public key, first 16 bytes, written with the letters a-p.
$der = [Convert]::FromBase64String($manifest.key)
$hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash($der)[0..15]
$id = -join ($hash | ForEach-Object { [char](97 + ($_ -shr 4)); [char](97 + ($_ -band 15)) })
$cmd = Join-Path $native 'agentdesk_host.cmd'
$hostPy = Join-Path $native 'agentdesk_host.py'
"@echo off`r`n`"$py`" `"$hostPy`" %*`r`n" | Set-Content -Path $cmd -Encoding ascii
$json = [ordered]@{ name = $name; description = 'Agent X Browser Bridge'; path = $cmd; type = 'stdio'; allowed_origins = @("chrome-extension://$id/") } | ConvertTo-Json
$jsonPath = Join-Path $native "$name.json"
$json | Set-Content -Path $jsonPath -Encoding ascii
foreach ($k in $keys) { New-Item -Path $k -Force | Out-Null; Set-ItemProperty -Path $k -Name '(default)' -Value $jsonPath; Write-Host "registered $k" }
Write-Host "Extension id: $id"
Write-Host 'Done. In Chrome or Edge open the extension popup and press Reconnect now: the channel should read native.'
