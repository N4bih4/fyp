# Windows integration checklist

20 October Phase 1 results: actual volume 50→49→50, brightness 52→51→52 and Bluetooth on→off→on passed and restored; Wi-Fi get passed. Live API relative correction opened `D:\6th sem\CN\lab`; Windows Update Settings launch accepted. Wi-Fi off/on and visual inspection of all Settings pages remain outstanding. Missing/undeployed labels in the original baseline below are historical; see FEATURE_AUDIT.md update for current status.

Audit baseline: 19 October 2026. This is a test plan, not a record of passes. See FEATURE_AUDIT.md for actual evidence. Execute after the relevant phase is approved and deployed.

Record Windows version, device model, runtime interpreter, application revision, requested command, resolved tool/target, observed state, and restoration result. Never include secrets or personal message contents in logs.

## Baseline and startup

- Start through START_AGENT_X.cmd; confirm backend health and frontend on port 8000. Check for duplicate listeners before starting another instance.
- Restart once with a harmless pending task: interrupted work must not replay automatically.
- Verify the backend virtual environment is selected, and missing capabilities produce actionable errors.

## Hardware and Settings

- Read volume, brightness and Bluetooth state repeatedly. These reads passed on the audit PC; repeat after changes.
- Record original volume, change by a small amount, verify actual readback, then restore. Test mute separately. Parser success alone is insufficient.
- Record brightness, change slightly, verify the physical screen and readback, then restore. Report unsupported external monitors accurately.
- Bluetooth off currently fails with a missing Radio import. After repair, use a built-in keyboard/mouse, record state, test off/on and restore. Check denial and missing-adapter behavior without changing Windows security settings.
- Wi-Fi is not implemented at this baseline. Authorize a controlled off/on test separately because it interrupts connectivity; prepare local recovery instructions and avoid remote-only access.
- Direct Settings routing is missing at baseline. After implementation, verify root, display, sound, Bluetooth, Wi-Fi, lockscreen and Windows Update pages. Do not install updates or change security settings during navigation tests.

## Conversation and files

- Test English, Roman Urdu and Urdu commands through text first; then voice. Record transcription and resolved intent separately.
- Test increase/decrease, on/off, misspellings and clarification. Unsupported commands must not report completion.
- Use a dedicated temporary directory with duplicate lab/lecture names. Test first/second choice, rejection, corrected relative path and preservation of the original operation.
- D:\6th sem was opened successfully; D:\6th sem\cn\lab exists, but the relative-correction source fix was not deployed at audit. Verify opening only after deployment. Do not use these real folders for destructive tests.
- In the temporary directory only: create, copy, move, rename, Trash and restore. Reject an action and prove no mutation occurred. Confirm path traversal and out-of-scope writes fail.
- Test archive collisions and expansion limits after the safety phase; do not extract untrusted archives into personal folders.

## Browser and media

- Install the supplied extension in the intended Chrome/Edge profile and verify bridge connection. This was disconnected at audit.
- With dedicated test tabs, verify exact close, duplicate-site selection and stale-URL rejection; unrelated tabs must remain open.
- Pause a playing YouTube video twice: it must remain paused. Resume twice: it must remain playing. Verify the intended tab and actual playback state.
- Test named-video selection and autoplay denial. Search results alone do not prove playback.

## Task control and integrations

- Use a controlled slow test transfer. After cancellation, prove network/process activity and file growth stopped; a cancelled database label is insufficient. Current cancellation does not establish this guarantee.
- Test timeouts against controlled slow operations. Ensure the API returns and the worker stops where promised.
- Test simultaneous approvals to prove one action executes only once after execution locking is implemented.
- Use dedicated accounts and dummy content for email/WhatsApp/Drive. Confirm recipient and content before send/upload; cancellation must leave the message unsent. No authenticated adapters are available at baseline.
- Test missing keys and provider limits without exposing credentials. Optional live provider tests require configured credentials and may incur cost.
- Test microphone permission denial, stop-listening behavior, accent recordings with consent, keyboard-only navigation and screen-reader status announcements.
- Test a packaged build on a fresh Windows account only after packaging repair; source-launch success does not validate an executable.
