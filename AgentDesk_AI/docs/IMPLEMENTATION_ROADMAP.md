# Phase 1 delivery update — 20 October 2026

User approved Phase 1. Bluetooth repaired and actual off/on verified; volume/brightness setters and restoration verified; Wi-Fi schema/routing/radio control added with actual read plus mocked off/on; direct Settings tool added; relative folder correction deployed and live OS-open request verified. Native workers remain bounded, and radio changes check both access status and final state. Legacy correction prose wrapping removed; candidate replies bind to the selected task and preserve destructive approval.

Remaining Phase 1 acceptance checks: controlled live Wi-Fi off/on requires explicit test authorization and recovery plan; visible-page verification for each Settings page; broader hardware/device coverage. No new standalone capability dashboard was added: current get operations and explicit errors provide per-control diagnostics. Bluetooth/Wi-Fi changes keep confirmation because peripherals/connectivity may disconnect. Later phases are not implemented or approved by this update.

See FEATURE_AUDIT.md for exact evidence and verify_phase1.py for reproducible read-only/default or restoring control checks. The original proposal below is retained for scope history; its pending-deployment statements are superseded by this update.

---

# Prioritized implementation roadmap

Date: 19 October 2026. Approval gate: the user's pasted brief explicitly requests audit and proposed phases before substantial changes. This document proposes scope; it does not grant approval. No replacement/rewrite of the whole project is proposed.

## Phase 1: repair daily PC controls and correction routing (proposed next)

Existing: isolated hardware reads, local multilingual parsing, file discovery/approval, backend-venv launcher, tested but undeployed relative-path reply fix.

Changes:
1. Fix the Bluetooth Radio import, check returned RadioAccessStatus, poll bounded readback and report actual on/off. Distinguish missing adapter, OS denial, hardware switch and unsupported operation.
2. Add Wi-Fi get/on/off through supported Windows radio APIs using the same bounded worker and actual-state verification. Do not weaken security or silently elevate.
3. Add an allow-listed Windows Settings tool: root, display, sound, Bluetooth, Wi-Fi, lockscreen and Windows Update. Natural phrases route directly to the proper ms-settings URI. Opening a Settings page is not changing it.
4. Finish the scoped correction pipeline. Resolve relative paths under known discovery roots, preserve original operation, remove legacy prose-wrapping fallback, and retain target choices across rejection/selection. Start with the exact D:\6th sem\cn\lab regression; avoid granting write access to D: implicitly.
5. Audit direct-command risk treatment so everyday controls do not ask meaningless confirmations while destructive actions remain explicitly gated. No blanket approval override.
6. Add real capability diagnostics and explicit distinction between a read test and a successful setter.

Files: tools/system.py, system_worker.py, registry.py, new settings tool, ai/speech_commands.py, command_language.py, orchestration/local_agent.py, executor.py, main.py, schemas/config as needed, frontend reply/settings controls, associated tests/docs.

Dependencies/cost: installed Windows radio/audio/brightness libraries; Settings URIs require no new cloud service. Wi-Fi testing can interrupt network and must be scheduled with a recovery path. No paid model call needed for these actions.

Acceptance: repeated volume/brightness supported changes read back correctly; Bluetooth off and on verified on this PC where supported; Wi-Fi read plus controlled off/on only with explicit test authorization; requested Settings pages open directly; correction preserves operation and requires fresh destructive approval; UI reports actual failures. Use temporary files for destructive tests.

## Phase 2: execution safety and honest task management

Existing: task/action DB statuses, manual approvals, rate-limit pause/resume, bounded native workers, basic startup interrupted-task recovery.

Changes: execution leases/locks, server-controlled approval policy, operation-specific cancellation tokens and process handles, cancellation acknowledgement, meaningful byte/progress states, robust timeout semantics, supported/unsupported pause distinctions, safe partial-file cleanup, archive overwrite/expansion checks and path-policy consistency.

Files: executor/models/main/schemas, tools/web/packages/filesystem/desktop, frontend task controls, security tests.

Dependencies/cost: local implementation; resumable HTTP requires server range support and validator checks. Some actions cannot safely pause; declare that rather than simulate it.

Acceptance: cancel a dedicated slow test transfer and prove it stopped; restart/resume only supported transfers; no duplicated actions under simultaneous API requests; approval cannot be skipped through an untrusted payload; unsupported pause is clearly refused.

## Phase 3: structured conversational context and chat UX

Existing: four recent task summaries, local workflow JSON, basic candidate numbers and setting follow-ups, browser Web Speech input/TTS.

Changes: session-scoped intent/entities/choices/history, label and ordinal selection, pronouns/rejected-choice tracking, bounded multi-step plans, semantic routing separated from authorization, clarification when uncertain; optional cloud interpretation controlled by cost/privacy settings. Replace raw developer cards as the primary experience with chat/results/choices while preserving diagnostics on demand. Add modal focus management and keyboard/screen-reader tests.

Dependencies/cost: broader free-form reasoning may require Groq or an explicitly configured local model. A local rule pipeline is not a trained LLM. Do not promise unlimited free reasoning or every accent.

Acceptance: representative English/Urdu/Roman Urdu multi-turn scenarios (including not that one, second one, SDI one, same folder) retain the correct action and never invent targets. Voice tests use representative recordings with consent and separate STT from intent accuracy.

## Phase 4: browser/YouTube integration

Existing: extension source, authenticated local socket, mocked tab/media tests; extension disconnected at audit.

Changes: enable bridge in intended Chrome/Edge profile with user consent, test exact real tabs, focus/navigation/search flows, selected-video results, previous-video state, precise stop vs pause vs close behavior; downloads integration only with suitable permissions and a real cancellation interface.

Files: browser_bridge.py, tools/browser.py, browser-extension, browser_commands.py, frontend integrations UI/tests.

Dependencies: one-time extension installation; logged-in sessions where required. Codex in-app browser cannot host this extension. No captcha/security bypass. No Groq needed for routine tab control.

Acceptance: duplicate-site tabs require selection; named background tab closes while unrelated tabs remain; repeated pause never resumes; expected-URL guard prevents stale actions; autoplay denial is accurately surfaced; selected video and resulting playback state verified.

## Phase 5: email, WhatsApp and Drive workflows

Existing: app open, exact mailto draft only; no authenticated account adapters.

Changes: choose supported interfaces before promising features. Add recipient/contact resolution, explicit recipient+content preview, editing, draft persistence where supported and separate confirmation for send/upload. Verify sent state through the interface rather than claiming delivery from a click.

Dependencies: account login/OAuth/provider permissions or supported authenticated browser adapters, dedicated test accounts; official product limits may constrain WhatsApp automation. Never collect passwords/tokens in chat. Design consent and cost disclosures before implementation.

Acceptance: ambiguous contacts are never auto-selected; messages remain drafts until confirmed; real provider result establishes sent status; failures/authentication requirements are honest. If a reliable interface is unavailable, document that feature as blocked.

## Phase 6: voice adapters, Windows matrix and packaging

Existing: browser-dependent speech services, source launcher, old unverified PyInstaller scripts.

Changes: swappable STT/TTS contracts; evaluate optional offline recognition against this PC's resources; regression recordings, hardware/Windows/device matrix, capability report, sanitized diagnostics, setup consolidation; make frozen worker entry points and frontend/extension resource packaging explicit; reproducible build and fresh-PC install test.

Dependencies/cost: optional local speech model downloads/storage/CPU, optional online speech pricing and consent. Do not install large models or packages without agreed need.

Acceptance: clean setup on a fresh Windows account, verified microphone stop/hands-free flow, supported device failures handled, executable starts correctly and hardware worker does not recursively start the app. Update audit after each phase.

## Decisions requested

Approve Phase 1 first, or adjust its scope. Later phases remain proposed. Preserve earlier tested fixes; deploy the path-correction patch as part of the approved Phase 1 instead of silently claiming it is already live.
