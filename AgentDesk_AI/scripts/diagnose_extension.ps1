# Finds out why the browser extension shows as "not connected". Run from AgentDesk_AI\ while the assistant is running:
#   powershell -ExecutionPolicy Bypass -File scripts\diagnose_extension.ps1
# Each line says OK / PROBLEM and what to do. Nothing is changed.
$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$script:bad = 0
function Line($ok, $what, $fix) {
  if ($ok) { Write-Host "OK       $what" }
  else { $script:bad++; Write-Host "PROBLEM  $what"; if ($fix) { Write-Host "         -> $fix" } }
}
$shipped = (Get-Content (Join-Path $root 'browser-extension\manifest.json') -Raw | ConvertFrom-Json).version
Write-Host "Extension files on disk: version $shipped"
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen
Line ($null -ne $listener) 'Something listens on port 8000 (the app)' 'Start START_AGENT_X.cmd. The extension can only connect while the app runs.'
$st = $null
try { $st = Invoke-RestMethod 'http://127.0.0.1:8000/browser/status' -TimeoutSec 4 } catch { }
Line ($null -ne $st) 'The app answers /browser/status' 'The app is not reachable on port 8000 (another program uses the port, or the app crashed: see logs\backend.log).'
if ($st) {
  Line ($st.connected) "A browser extension is connected ($($st.profiles) profile(s))" 'Open the extension popup (puzzle icon, Agent X Browser Bridge). If it says Not paired, open the setup page from the app and pair. If the app was not running, press Reconnect now.'
  foreach ($c in $st.clients) { Write-Host ("         {0} extension {1}, last heard {2} s ago, focused={3}" -f $c.browser, $c.version, $c.heard_seconds_ago, $c.focused) }
  Line (-not $st.outdated) "Extension version matches the files ($($st.version) vs $($st.expected_version))" 'Open chrome://extensions or edge://extensions and press Reload on Agent X Browser Bridge (it also reloads itself when connected).'
  Line (-not $st.ambiguous) 'Only one browser is in use, or one was focused last' 'Chrome and Edge both run the extension: click the browser you want to use once so it is the focused one, or disable the extension in the other.'
}
Write-Host ("Browsers running: chrome={0} edge={1}" -f [bool](Get-Process chrome), [bool](Get-Process msedge))
foreach ($pair in @(@('Chrome', 'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.agentdesk.bridge'), @('Edge', 'HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.agentdesk.bridge'))) {
  $state = if (Test-Path $pair[1]) { 'registered' } else { 'not registered' }
  Write-Host ("NOTE     {0}: native messaging host {1} (optional; keeps the extension awake)" -f $pair[0], $state)
}
Write-Host 'To register the native host: powershell -File scripts\install_native_host.ps1'
Write-Host ''
if ($script:bad -eq 0) { Write-Host 'No problem found on the app side. If the popup still says disconnected, press Reconnect now and read its Last problem line.' }
else { Write-Host "$($script:bad) problem(s) found." }
exit $script:bad
