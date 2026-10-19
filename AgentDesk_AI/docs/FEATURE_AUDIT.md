# Phase 1 update — 20 October 2026

## Shared lifecycle routing follow-up

Added a shared bounded target/action grammar for on/open/start and off/close, across known apps, sites, Settings and explicit folder nouns. Device semantics and negation remain validated by the setting parser. A brief follow-up uses only the immediately preceding successful app/site/device task; failed or unrelated work is not searched past to infer an old target. Explicit Chrome selection is retained.

PowerShell actual-PC check: initial launch was hidden; launching this requested interactive app now uses CREATE_NEW_CONSOLE. A visible PowerShell window hosted by Windows Terminal was observed with HWND/PID, then closed through its exact identity after task approval. Zero matching windows remained; backend health stayed ok. Batch closes require review and mention that other tabs in a Terminal window may also close. No unrelated processes are killed.

Chrome/YouTube opening limitation discovered during paired testing: native Chrome process launch alone did not establish a YouTube tab in the connected profile. Do not treat that as end-to-end open success. The bridge now supports verified tab creation/activation in its own profile and checks Chrome versus Edge. The already-loaded extension must be reloaded once at chrome://extensions to activate this new handler. Until then the backend returns an explicit Reload error instead of silently falling back to an unverified profile. Existing close-tab live verification remains valid. New profile-bound open requires actual-PC verification after reload.

Verification snapshot: full backend suite 300 passed/1 skipped before the final narrow follow-up/profile changes; subsequent targeted suites passed (53 for context/routing, then 51 for final browser/context changes). Extension mock controls, including create/reuse/profile mismatch and URL validation, passed. No claim that every application or free-form sentence is supported.

## Latest live audio and browser verification

Supersedes older browser-disconnected and mute-state notes below. One browser extension profile is now connected.

- Exact `والیوم اپ کرو`: actual Windows volume **60→70**, mute **True→False**. Increasing volume now clears mute; a positive explicit set does too. Decrease does not deliberately unmute.
- Exact `ان میوٹ پی سی`: split Urdu unmute normalization fixed; live task completed and actual GetMute returned False. Native mute/unmute checks GetMute after SetMute and fails on mismatch.
- Exact `یوٹیوب کروم میں کلی ہوئی ہے وہ والا ٹیب بند کرو`: known-site extraction now removes only allow-listed conversational descriptors. Live corrected request closed the single YouTube tab, confirmed by the extension; before/after tab-ID comparison showed exactly that one removal, with the other four tabs retained. Duplicate-site behavior still requires selection. Unknown title qualifiers and requests naming multiple sites are preserved rather than broadened.
- Full backend regression suite **275 passed, 1 skipped**. Changes deployed. PC left at volume 70 and unmuted following the user's requests.

## Reported-command follow-up (same date)

- Actual original `میوٹ پی سی` request completed through the live API, and a separate Windows EndpointVolume.GetMute read returned True. PC was left muted as requested.
- Actual original `ٹرن ان بلو ت` request resolved to Bluetooth/on, received task-specific approval and completed with bounded radio-state verification.
- `ٹرن اف سیٹنگ` now routes to closing a named window. If no matching window is open, the app says so. A controlled Settings-open → original Urdu close request completed; desktop verification reported closed=True for exactly Settings. General apps/folder windows have routing tests but were not all live-closed.
- `یوٹیوب کلوز` now routes to control_browser/close/youtube. Live execution is **blocked** because zero browser extension profiles are connected. It reports the concrete extension error rather than an unclear-command note. Available UI inventory exposes no Chrome/Edge browser, so extension installation cannot be completed from this session. The frontend now shows a setup link next to voice controls.
- A clear new local command now supersedes a pending folder clarification; it cannot be consumed as the old workflow's path reply. Window choices are task-bound; exact current title is required at close time, including revalidation of uniqueness.
- Backend regression suite: **263 passed, 1 skipped**. Frontend build passed. Voice helper tests: four passed. Short localized TTS, active recognition during speech, interim-text interruption, acknowledgement consumption and Stop speaking button are implemented; actual microphone/echo performance remains unverified.

These findings supersede the older baseline claims for these exact controls, without claiming a complete conversational assistant.

This update supersedes the Bluetooth, Wi-Fi, Settings and correction findings in the original baseline below. User approved Phase 1; later phases remain proposed.

| Capability | Current status | Evidence / remaining limit |
| --- | --- | --- |
| Bluetooth get/off/on | Fully implemented and tested on this PC | Actual on→off→on with readback; original state restored. Missing Radio import fixed; access result and bounded transition checks added. Other hardware/policy combinations still vary. |
| Volume/brightness adjustment | Fully implemented and tested for percentage setters on this PC | Volume 50→49→50; brightness 52→51→52. Both restored. Mute and other devices not newly live-verified. Inaccurate percentage readback now fails. |
| Wi-Fi get/on/off | Implemented but not adequately tested | Real get reports enabled; mocked off/on and wrong-adapter guards pass. Live off/on deliberately not run because it disconnects the network. |
| Direct Settings navigation | Implemented but not adequately tested | Allow-listed root/display/sound/Bluetooth/Wi-Fi/lockscreen/Windows Update; multilingual routing tests pass. Windows Update launch accepted through live API; exact visible page still requires UI verification. No setting changed by this navigation tool. |
| Task-bound folder correction | Partially implemented | Deployed. Live reply `6th sem/cn/lab` resolved to `D:\6th sem\CN\lab` and OS opener succeeded. Mock tests prove numbered choice retains delete operation and fresh approval. Unknown corrections retain context; legacy prose-wrapper fallback removed. Broad pronoun/ordinal conversation still belongs to Phase 3. |

Verification: full backend suite **236 passed, 1 skipped**; after one additional Wi-Fi regression, the final Phase 1 suite **29 passed**. Frontend TypeScript/Vite build passed. The optional cloud test remains skipped. Tests do not establish all Windows/device combinations.

Backend restarted through the source launcher and health checked at http://127.0.0.1:8000. No new dependencies or paid API calls. Bluetooth and Wi-Fi changes retain medium-risk confirmation; reads and Settings navigation are low risk. No blanket approval bypass was added. Existing cancellation/authentication/archive/packaging findings below remain open.

---

# Feature audit: AgentDesk / Agent X AI

Audit date: 19 October 2026 (client date). This is a source-code and evidence audit, not a statement that the full product is complete. Requested substantial implementation phases await approval after this audit.

## Evidence and review boundary

Reviewed backend API, schemas, SQLite models/migrations, provider selection and SDK adapters, orchestration/local routing, tool registry, filesystem/system/desktop/browser/package/web tools, permission/path helpers, launcher, build specification, Windows verification script, frontend API client/chat-task UI/voice/CSS/Vite configuration, browser extension, tests, and existing documentation. API keys and tokens are not reproduced here. No destructive tests were run against real files. No new dependencies, security policy changes, account integrations or paid generations were introduced for this audit.

Current full backend regression run: **208 passed, 1 skipped**. The skipped test is an opt-in live Groq test. TypeScript/Vite production build passed after the path-reply changes. Node browser-extension checks passed using mocked Chrome APIs. Tests run primarily under the workspace test environment; live device checks used backend/.venv.

Live evidence from this session:
- Local backend/frontend health and same-origin page/API requests succeeded.
- Repeated isolated volume reads succeeded (100%); brightness read succeeded (52%); Bluetooth read succeeded (on). These are READ checks, not proof of setting changes.
- The user's D:\6th sem was discovered, selected and opened by the app.
- D:\6th sem\cn\lab exists. The newly added relative-correction patch passes isolated/API regression tests but has not been deployed to the running server or live-opened yet.
- A user-authorized real Bluetooth-off attempt returned `name 'Radio' is not defined`. It did NOT turn Bluetooth off. This is a code/import defect, not demonstrated Windows denial.
- Browser bridge reports disconnected; no real Chrome/Edge tab close or YouTube pause/resume has been demonstrated.
- Existing OpenAI credentials previously failed a read-only model lookup with HTTP 401; Gemini key was absent. Backup generations are not verified. No new credential test was performed for this audit.

Status meanings:
- **Fully implemented and tested**: only the precise bounded scope described in that row is established.
- **Implemented but not adequately tested**: code exists, but live/integration evidence is insufficient.
- **Partially implemented**: meaningful pieces exist; the requested end-to-end behavior is incomplete or broken.
- **Missing**: no adequate implementation found.
- **Blocked by Windows permissions or external API requirements**: requires a concrete external setup, consent, account or hardware capability; this does not imply the code is otherwise complete.

## Feature matrix

| Feature and bounded scope | Status | Implementation | Verification / limitations |
|---|---|---|---|
| Registered tool names and Pydantic argument validation | Fully implemented and tested | backend/app/tools/registry.py, tools/base.py, ai/planner.py | Unit/API tests reject unknown tools and malformed arguments. Does not establish authorization of every valid action. |
| Local command variants covered by tests | Fully implemented and tested | ai/speech_commands.py, command_language.py, browser_commands.py | Actual failed Urdu transcripts and English/Roman Urdu/Hindi examples have regressions. Only tested patterns; not arbitrary conversational understanding. |
| General natural conversation, pronouns, yesterday/previous activity | Partially implemented | orchestration/local_agent.py, executor.py | Recent-task memory and local workflow state exist. No full entity/reference model, recency/activity index or general conversation engine. |
| Numbered folder discovery and preview/confirmation | Partially implemented | local_agent.py, tools/filesystem.py | Tested exact numbered choices and preview -> yes. Broader replies such as second one/SDI one are not generally resolved. |
| Scoped relative-path corrections | Partially implemented | local_agent.relative_candidates/correction_plan, main.reply_task, frontend/src/App.tsx | New regressions cover 6th sem/cn/lab and cn/lab; traversal rejected. Patch not yet live deployed; application/file inference and fallback wrappers still need consolidation. |
| File/folder search | Partially implemented | tools/filesystem.py, tools/base.py, config.py | Bounded name/fuzzy/limited bilingual discovery; configured read-only roots. Not full-drive indexing, file-content search or yesterday activity search. Depth/visit limits may omit matches. |
| Open selected existing folder | Fully implemented and tested | filesystem.OpenFolderTool, local_agent.py | Actual D:\6th sem opened. Opening an arbitrary file with its default application is a separate scope. |
| Open arbitrary files | Implemented but not adequately tested | filesystem.OpenFileTool | Unit coverage; no broad live validation by file type/default handler. |
| Application aliases and launch | Partially implemented | tools/apps.py | Start Menu, registry/PATH and known aliases; tests mock launches. Reuse may choose first of multiple matching running windows. Verification mostly reports successful launch request, not usable app state. |
| Window close/minimize/maximize/restore | Implemented but not adequately tested | tools/desktop.py | Bounded target validation and foreground checks are tested. Generic conversational routing, switch/focus and real app/save-dialog behavior need integration tests. |
| Volume/brightness/Bluetooth read | Fully implemented and tested | tools/system.py, system_worker.py | Live repeated isolated read checks succeeded on this PC. This row does not cover mutations. |
| Volume increase/decrease/mute/unmute | Implemented but not adequately tested | tools/system.py | Bounded args, isolated workers and mocked changes tested. Live repeated setters, mute readback and audio-device changes need verification. Mute currently reports requested state without actual mute readback. |
| Brightness adjustments | Implemented but not adequately tested | tools/system.py | Uses first controllable display. Setter reads back value, but equality/tolerance vs requested value is not fully enforced. External monitors/multiple displays not verified. |
| Bluetooth on/off | Partially implemented | system._set_bluetooth | CONFIRMED NameError: Radio imported in another function but referenced here without import. Medium-risk approval also prevents immediate execution until confirmed. Permission behavior cannot be assessed before fixing defect. |
| Wi-Fi on/off/status | Missing | system schema/parser currently excludes wifi | RadioKind.WI_FI exists in installed SDK; no wifi tool implementation or verified switching. Do not disable network during audit. |
| Dark/light mode | Implemented but not adequately tested | tools/system.py, frontend/src/index.css | Registry write/readback and broadcast code, mocked tests, current theme live READ. Actual dark/light switching and application adoption not verified. |
| Screenshot | Implemented but not adequately tested | system.TakeScreenshotTool | Approval and file verification code/tests. No new live capture audit; may contain private content. |
| Direct Settings pages: display/lockscreen/update/network | Missing | No dedicated settings tool or ms-settings allow-list | Generic app lookup is not a reliable Settings page workflow. Microsoft URI mapping verified as design input. |
| Ordinary website open/search | Implemented but not adequately tested | apps.OpenUrlTool/WebSearchTool | Local routing and browser handler tests; browser/search result availability not exhaustively live checked. |
| Exact browser tab close and metadata | Blocked by Windows permissions or external API requirements | browser_bridge.py, tools/browser.py, browser-extension | Code, authenticated socket round-trip and mocked tab selection tested. Chrome/Edge extension not enabled; actual tabs remain unverified. Multiple profiles deliberately rejected. |
| Tab focus/switch/navigation and arbitrary page controls | Missing | Current bridge supports inspect/close/pause/resume only | Desktop hotkeys do not supply reliable background tab/app DOM control. |
| YouTube pause/resume | Blocked by Windows permissions or external API requirements | browser_commands.py, tools/browser.py, extension/background.js | Mocked idempotent pause/resume and navigation guard tests. Requires connected extension and actual playable YouTube video; autoplay may block resume. |
| YouTube stop vs close vs change video | Partially implemented | browser_commands.py, apps.PlayYouTubeVideoTool | Stop currently maps to pause; close-video phrase is not a complete workflow. Named-video lookup may auto-pick a heuristic match rather than show/select alternatives. |
| Named YouTube search/play | Partially implemented | apps._find_youtube_video, PlayYouTubeVideoTool | HTML lookup and fallback tested with mocks. Autoplay not guaranteed. Suitable result choice and replace-current-video workflow incomplete. |
| WhatsApp open | Partially implemented | apps.py, command aliases | Generic installed app launch/site handling only. Not evidence of contact/message access. |
| WhatsApp contact search/read/draft/send | Missing | No contact API/DOM adapter or send workflow | Logged-in session and an authorized supported interface required; no contacts or delivery claims can be inferred. |
| Email draft from explicit recipient/subject/body | Implemented but not adequately tested | apps.ComposeEmailTool | Opens mailto draft, does not send. Default mail handler/account setup and actual saved draft behavior unverified. |
| Natural email generation/contact lookup/save/send | Partially implemented | optional cloud prose plus compose_email | No recipient directory/OAuth provider, draft persistence or verified sending. Sending must remain gated. |
| Drive file search/upload/download/cancel | Missing | Browser tab matching is not a Drive file integration | OAuth or supported authenticated browser workflow needed. |
| Create/copy/move/rename/write/read files | Partially implemented | tools/filesystem.py | Meaningful temp-dir tests; policies vary by tool. Large/locked files, permission failures, symlink/junction races, overwrite consistency and full user-level workflows need hardening. |
| ZIP compress/extract | Partially implemented | filesystem.CompressFolderTool/ExtractFileTool | ZIP-slip checks and temp tests exist. Extraction may overwrite existing files and has no total uncompressed-size/member-count budget. |
| Recoverable deletion/restore | Partially implemented | filesystem.DeleteFileTool/RestoreFileTool | Internal Trash, approval, temp folder/restore tests exist. Not Windows Recycle Bin; path policy is broader for empty-item deletion. Preflight/TOCTOU consistency needs work. |
| Direct URL download | Partially implemented | tools/web.py | 20 MB limit, public host checks, temporary file and size verification. No cancellation token/progress/resume, DNS re-resolution race and destination race need review. |
| App installer discovery/download | Partially implemented | tools/packages.py | WinGet search/show/download, exact IDs and child timeout. No real app-download integration run; source terms/Store sign-in may block. Does not install. |
| Software install | Missing | Installer launch intentionally absent | Requires exact publisher/package review and explicit installation approval. |
| Task identity/history/approval | Partially implemented | models.py, executor.py, main.py | Persisted IDs and action statuses, early-resume guard and creation idempotency tested. No atomic execution lease/per-task concurrency lock or session identity. |
| Stop/cancel an ongoing download | Missing | cancel_task changes task metadata only | In-flight HTTP/WinGet operations do not acknowledge cancellation. Cancelled is not proof of underlying stop. |
| Pause/resume long-running operations | Partially implemented | provider cooldown waiting_retry | Cloud-turn resume preserves completed actions. This is NOT download pause/resume or general process suspension. |
| Effective general tool timeout | Partially implemented | executor._run_with_timeout | ThreadPoolExecutor context waits for running thread at shutdown after timeout. Hardware workers and WinGet have separate child timeouts; arbitrary tools do not have reliable hard cancellation. |
| Groq tool-calling loop | Partially implemented | ai/groq_provider.py, executor.py | Scripted loops/429/error tests; live test skipped. Quota/key/account access affect real availability. |
| Cloud backup providers | Blocked by Windows permissions or external API requirements | ai/resilient_provider.py, planner.py | Adapters and mocked failover tested. No valid verified active backup; model/account availability unverified. |
| Provider consistency | Partially implemented | ai/openai_provider.py vs resilient_provider.py | OpenAI primary uses static JSON plans; backup uses agent loop. Primary uses shared AI_MODEL, which may still be a Groq model ID. Gemini is backup-only. |
| Speech input/hands-free/TTS | Partially implemented | frontend/src/App.tsx | Browser speech and synthesis; visible mic, stop, queue, 2.2 s transcript debounce. No representative accent recordings, offline STT, replaceable provider interface or measured interruption handling. |
| Chat UX/accessibility | Partially implemented | frontend/src/App.tsx, index.css, api.ts | Task cards, raw args/results, history, approvals, connection retry and OS theme CSS. Not a full chat transcript; modal focus/keyboard behavior and visual accessibility not systematically tested. |
| Source startup/reconnect | Partially implemented | launch.py, run_server.py, Vite proxy, API client | Health/readiness, correct backend venv preference and repeated launch tested. Several venvs exist; diagnostics and controlled upgrades need improvement. |
| Windows executable distribution | Missing | agentdesk.spec/build_windows.ps1 are preparatory | No verified executable. Static UI/extension/Groq resources not comprehensively bundled; sys.executable -m worker must be adapted for frozen execution. |

## Priority findings

### P0: correct misleading or unsafe behavior

1. Bluetooth mutation fails due missing Radio import. This is reproduced on the real PC; no off success was observed.
2. Task cancellation updates database state without cancelling the underlying tool. UI must distinguish requested/acknowledged/unsupported cancellation.
3. Generic timeout is not a hard stop: the executor waits for the thread on context exit. Do not report safe cessation from that timeout alone.
4. HTTP clients can send auto_approve=true, bypassing approval for every risk class. There is no user authentication; CORS is not authentication. Restrict this override to explicit trusted/test configuration before expanding capabilities.
5. Named-app desktop risk heuristics can downgrade arbitrary keyboard/mouse sequences. They do not enforce the semantic boundary between drafting vs sending/uploading/destructive clicks. Prompt instructions alone are insufficient.
6. ZIP extraction does not refuse per-entry overwrite or constrain archive expansion. Keep unsafe overwrite behavior out of the approved phase.
7. Concurrent run/reply/approve requests lack an execution lease/atomic state transition, allowing races despite idempotent creation.

### P1: conversation, routing and policy consistency

- Local agent is a growing rule set; requiring AI: for unmatched language does not meet the full natural conversation requirement. Recommend a bounded local-first intent/context router with optional cloud-assisted clarification, explicit cost/privacy settings, and no model authority over permissions.
- Relative correction and task-scoped reply changes are present and tested but not yet deployed. Fallback still has a legacy wrapped Original request branch that can strand other corrections.
- Selection handles numbers and a narrow yes/no set; second one, distinguishing labels and rejected-choice memory need structured candidate state.
- Search truncation/limited aliases are not full language understanding or activity history. The supplied discovery root grants read discovery, not write access; D-drive mutation may correctly remain blocked.
- create-folder and empty-item delete are broader than the write allow-list used by copy/move/rename. This needs one documented, user-visible permission policy.
- Stop/close semantics for YouTube differ from the new brief and need explicit resolution.

### P2: hardening and delivery

- Public URL validation and HTTP connection resolve DNS separately; pin/validate connected destination for stronger SSRF protection. File preflight vs mutation also needs race-resistant checks.
- Browser extension token/Origin checks are separate from unauthenticated PC APIs. Add a coherent trusted-local-client/session model rather than treating custom headers as general authentication.
- build_windows.ps1 installs a dependency, and verify_windows.py assumes older tool counts/static mock flows. Do not run those scripts as proof that the modern project is ready.
- Older SECURITY/DEPLOYMENT/SETUP docs conflict with current source: two-server advice, once-per-command LLM cost claim, old risk levels, empty-folder-only deletion and blanket no-file-content-to-provider claims. Documentation must track each runtime mode.
- Credentials/configured flags do not prove valid credentials, available quota or funded billing. Three venvs and multiple old SQLite locations can produce divergent state.
- Add install/runtime capability checks and logging that omits tokens, commands containing private content and account material as appropriate.

## Acceptance conclusion

This is a useful partial local desktop assistant with meaningful tested components. It is NOT yet a complete conversational PC agent, messaging assistant, reliable transfer manager or distributable Windows product. Passing mocked tests is not evidence of those integrations. Proposed work and approval gates are in IMPLEMENTATION_ROADMAP.md; safe live scenarios are in WINDOWS_TEST_CHECKLIST.md.
