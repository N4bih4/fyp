# Current setup, troubleshooting and integration requirements

## Phase 1 update (20 October 2026)

Shared lifecycle grammar now covers paired known-target requests: `PowerShell on/off`, `پاور شیل آن/اف`, `YouTube Chrome mein on/off karo`, and Settings/app equivalents. A short follow-up can reuse the immediate successful target. All-PowerShell requests inspect HWND/PID and require approval; Terminal windows may contain additional tabs, which the plan discloses. Actual visible PowerShell open/close passed after correcting hidden-console launching.

For the updated Chrome website-open handler, reload the already installed extension once: chrome://extensions → Agent X Browser Bridge → Reload. No new permission is added. The new handler creates/activates and verifies a tab in the connected profile, rather than assuming a native Chrome launch used that profile. Old loaded code returns an explicit Reload error. The new open handler has mocked tests but still needs live verification after reload. The extension's existing reconnect alarm may take about 30 seconds after backend restart; clicking its icon also reconnects.

Latest audio/tab repair: `ان میوٹ پی سی` now handles split Urdu unmute. Volume up also clears mute, fixing the case where the numeric level rose but audio remained silent. Windows mute changes check actual GetMute. Live verification: volume 60→70 and muted=True→False, followed by successful explicit unmute. The extension is now connected; the original conversational `یوٹیوب کروم میں کلی ہوئی ہے وہ والا ٹیب بند کرو` closed exactly the YouTube tab while four unrelated tabs remained. Earlier disconnected-extension notes below are historical. The parser strips only recognized site-description words; it retains meaningful unknown title qualifiers and still requires selection for multiple matching tabs.

Basic-command repair follow-up: `ٹرن ان بلو ت` now recognizes the short Urdu "on" transcription, and `میوٹ پی سی` has been executed successfully with actual Windows mute readback=True. A clear new command while a folder clarification is pending starts that command rather than becoming a folder path. `ٹرن اف سیٹنگ`, `اف سیٹنگ ونڈو`, `کلوز لیب فولڈر` and `اف لیب فولڈر` now inspect real window titles and plan an exact window close; multiple matches require a selection. Settings close was verified on a freshly opened Settings window. Closing a folder window does not delete its folder. Unknown/missing windows receive a specific message.

`یوٹیوب کلوز` and tab-off phrases route to the browser bridge. The bridge is currently disconnected, so real tab closing remains blocked until the extension is loaded in the user's Chrome/Edge profile. This session has no Chrome/Edge UI connection and cannot load it automatically. The app shows a direct setup link. Do not claim that a disconnected tab operation succeeded.

Speech UX follow-up: spoken output now uses short localized status sentences instead of reading full plans/errors (previously up to 500 characters). Full task details remain on screen. In hands-free mode the recognizer stays active during playback; interim user text cancels TTS, and final command text continues through the queue. Interruption acknowledgements such as `achha theek hai` are consumed, not sent as approval. A visible **Stop speaking** button cancels speech without stopping hands-free listening. This cancels audio playback, not an executing PC task. Exact own-reply echo filtering is provided, but speaker/microphone echo and browser recognition latency still require real-device checks; these are not a full acoustic echo canceller or offline speech engine.

Verification: four frontend voice-policy/lifecycle tests passed via `node --test voice.test.mjs`; TypeScript/Vite build passed. Backend transcript/local pipeline suites: 64 passed, including `میوٹ پی سی` → volume/mute. No microphone recording or real spoken interruption test was performed. After refreshing, enable hands-free, trigger a reply, interrupt with `اچھا ٹھیک ہے` and then `میوٹ پی سی`; verify speech stops, the acknowledgement does not approve an action, and the next command appears once. Also check speaker echo does not trigger commands; use Stop speaking if browser recognition does not detect the interruption.

Voice follow-up: `ہیں کلوز بلو ت`, `کلوز بلو ت`, `close blue tooth` and `ٹرن اف بلوٹوتھ` now route locally to Bluetooth off with confirmation. These narrowly scoped radio aliases do not rewrite file/app targets; negation and compound-action regression checks pass. The original failed task was reprocessed through UTF-8 JSON and produced an awaiting-approval Bluetooth-off action. No device change was performed for this check. Targeted routing suites: 92 passed; frontend build passed.

Reconnection follow-up: successful config polling now clears an old connection-error banner, while retaining unrelated command errors. Backend and supervisor were restarted and ports 8000/18000 verified. Refresh the page once after a frontend update to load the new assets. A launch-time outage during restart does not by itself establish a native crash; inspect backend.log for the actual event.

Bluetooth import defect fixed; real off/on passes on this PC. Wi-Fi local controls and direct Settings routing now implemented. Relative corrections deployed; `6th sem/cn/lab` resolves and opens through the live backend. Below is the retained audit baseline; its missing-feature/undeployed statements for these controls are superseded.

Try: `volume kam karo`, `brightness zyada karo`, `bluetooth off`, `wi fi on`, `wifi status`, `open settings`, `screen ki setting khol do`, `lock screen settings kholo`, `windows update settings`. Radio changes can ask confirmation; unsupported/denied devices return errors rather than claim success. Settings launch success means Windows accepted the launch request, not visual confirmation of the page. Wi-Fi live off/on is still unverified.

For actual-PC diagnostics from the backend directory, run `.\.venv\Scripts\python.exe verify_phase1.py` (reads only). `--change-controls` toggles Bluetooth and changes volume/brightness by 1%, restoring originals; use only when interruption of Bluetooth devices is acceptable. This script never toggles Wi-Fi.

Updated 19 October 2026. Read FEATURE_AUDIT.md and IMPLEMENTATION_ROADMAP.md before interpreting older demo guides as verified capabilities.

## Source setup on this PC

Use START_AGENT_X.cmd in the workspace root. The launcher prefers AgentDesk_AI/backend/.venv/Scripts/python.exe, which contains this PC's audio, brightness and Windows SDK dependencies. The workspace-root .venv is a test environment and does not have all hardware dependencies.

The source launcher serves the built frontend and API at http://127.0.0.1:8000. Port 5173 is the separate Vite development frontend. A frontend loading successfully does not establish backend health. Inspect launcher output and the listener before starting duplicate servers.

To avoid PowerShell activation-policy changes, invoke the virtual environment's python.exe directly. Use npm.cmd for frontend commands when npm.ps1 is blocked. Do not broadly weaken Windows security settings to fix startup.

## Known failures

- Bluetooth off: the observed error is `name 'Radio' is not defined`. This is a code defect, not a request for a password. The repair awaits Phase 1 approval.
- Wi-Fi controls and direct Settings-page routing: missing at audit; not fixed by adding an API key.
- Volume/brightness: repeated reads passed after hardware-worker isolation. Real setter verification remains outstanding; report unsupported hardware explicitly.
- Corrected folder paths: the source patch resolves paths under known discovery roots and preserves the operation, but it had not been deployed into the running backend at audit. D:\6th sem is a discovery root, not permission to modify the whole drive.
- Task cancellation: the current status label does not prove an in-flight action stopped. Do not rely on it for destructive actions.
- Provider quota: routine supported local commands do not need Groq. Unknown free-form requests can still need clarification; unlimited reasoning is not implemented locally.

## Browser setup

Open http://127.0.0.1:8000/browser-extension/setup.html while the backend runs. Follow the supplied guide to load AgentDesk_AI/browser-extension in the intended Chrome/Edge profile. This is a one-time user-controlled extension installation; the Codex in-app browser cannot host it. Verify connected status before testing tab/media commands. Mocked extension tests are not evidence of a live connection.

## External services, credentials and limits

| Capability | Requirement | Baseline limitation |
| --- | --- | --- |
| Local supported tools | Windows account and relevant device/API permissions | Hardware and OS support vary; no cloud key required |
| Groq reasoning | Valid Groq key and provider quota/billing | Rate limits remain provider-controlled; live test skipped in the audit suite |
| Optional AI backup | Separately configured compatible provider key/model | Gemini key absent; existing OpenAI credential previously returned 401; backup not verified |
| Browser tab/media | Installed extension, connected intended profile | Extension disconnected at audit |
| Voice | Microphone permission and browser speech support | Recognition may use browser online services; offline recognition not implemented |
| Email | Current mailto support requires a configured mail handler | No authenticated send, contacts or sent-state verification |
| WhatsApp/Drive workflows | Future supported account interface, login/OAuth and appropriate permissions | Contact messaging and Drive file APIs missing |
| Package downloads | WinGet availability, network and publisher/package verification | Download is not installation; no verified installer workflow |
| Packaged executable | Repaired build resources and fresh-PC testing | Existing packaging scripts unverified |

Store API keys in the backend's local configuration only; never paste keys, passwords, .env contents or access tokens into chat or diagnostics. Configuration flags alone do not prove credentials work. No new service purchase or dependency installation is required for the proposed local Phase 1.

Use WINDOWS_TEST_CHECKLIST.md for actual-PC acceptance checks. Record failures separately from mocked test results and update the audit after each approved phase.


## Logs and restarts

- Structured logs: `%LOCALAPPDATA%\AgentDesk\logs\agentdesk.log` (JSON, one event per line; search by `task_id` or the `X-Request-Id` response header). Launcher output is in `logs\launcher.log` and `logs\backend.log` next to the project.
- A task that says "Server restart se task interrupt hua" was running when the app stopped. Its last action may have changed things already: check the real file/folder state before repeating the command. Interrupted actions have no verified undo.
- Old finished tasks keep their history. To limit stored AI conversation and rollback backups, set `RETENTION_DAYS` in `backend\.env`; the default keeps everything.
