# Voice automation of the whole laptop: plan and build prompt

Goal (in the user's words): sign in, the orb is already there and listening. "Shadow, File Explorer kholo" -> then "C drive kholo" -> "Users"
-> "Documents" all go into the SAME window, as one continuing conversation (not one message, one answer, end). Several agents work at once, each in
its own app. Anything on the laptop can be done by voice in English, Roman Urdu, Hindi (and Urdu). When a request is ambiguous ("open a browser",
"open email") the agent ASKS instead of guessing. Every command must finish in 5 to 10 seconds.

Status as of 2026-11-13: what exists, what is missing, then the plan, then a paste-ready build prompt.

---

## 1. What exists today (verified in the code)

| Need | Today |
|---|---|
| Orb on screen from sign-in | `desktop/shell.py` (always-on-top orb, tray) + Run key (switched on 2026-11-13). Starts the backend itself. |
| Always listening | VAD + Whisper in the orb window (`frontend/src/speech`). Junk filter added (`voice/junk.py`). |
| Several agents | `agents/roster.py` (Shadow lead, Scout browser, Atlas files/system, Forge coding, Echo research), `agents/dispatcher.py` (one agent per job), `agents/splitter.py` (one sentence -> several jobs), Agents board on screen. |
| Continuing conversation | `orchestration/session.py` = ONE global task session. Soft limit 2 min of silence (then asks "end this task?"), hard expiry 10 min. `session_context.py` remembers one folder ("here", "go back"). |
| Controlling apps | tools: `open_application`, `ui_inspect`/`ui_act` (UI Automation), `screen_act` (OCR + vision), `control_desktop`, `explorer_view`, `manage_system_setting`, `open_windows_settings`, `device_control`, `control_browser` (extension 2.0), `drive_coding_agent` (Antigravity, Claude), email/WhatsApp flows, terminal, winget install/uninstall. |
| Browser profiles | `open_browser_profile` (asks when two profiles share a name). |
| Speed | local plan 22 ms median, cloud planner 5 s median / 25 s p90, transcription 2.2 s median. |

## 2. What is missing (the gaps this plan closes)

1. **Per-agent conversations.** There is one global session. Switching to another app/agent loses the first one's context. Needed: one *lane* per agent, each remembering its app, window, folder or page, last 20 steps.
2. **20 minute life, not 2/10.** A lane stays open 20 minutes after its last word, whatever the number of messages. Coming back inside 20 minutes: ask "Same File Explorer window, or a new one?".
3. **Ask-first policy.** Today `open_url` falls back to the default browser, "open chrome" is taken literally, "open email" is not handled as a question. Needed: a clarification engine that lists what is really installed (browsers, mail apps) and asks, in the user's language, every time (optional "always use X" the user can say once).
4. **Same-window continuity for File Explorer.** Navigation must act on the window the lane owns (by window handle), not on whichever Explorer is in front.
5. **Coverage of everything.** No inventory exists of "operations on a laptop"; we need a list (about 100) with a live check per item, so "each and everything" is measured, not assumed.
6. **Coding-app lanes.** Claude/Antigravity: new chat, pick the project folder through the app's own open-folder dialog, then dictate the prompt, watch it, read the result. Only the last step exists.
7. **Speed.** The local ONNX intent model (17 ms) is only logging (shadow). It should answer the common commands directly; the cloud planner stays for the rest.
8. **Real-voice data.** The model has only ~14 real sentences. Voice sessions with several speakers are needed (`docs/DATASET_GUIDE.md`).

Cannot be done (Windows security): power on, type the password, unlock. The orb starts after sign-in; that is the boundary.

## 3. Design

### 3.1 Lanes (the heart of it)
```
Lane { id, agent, kind: explorer|browser|app|coding|system|mail|research,
       target: { hwnd, process, title }, state: { folder|url|project|draft },
       history: last 20 steps, last_active, status: open|parked|closed }
```
* Created when an agent starts a job in an app. Stored in the DB (survives a backend restart) and reported by `GET /lanes`.
* **Routing of a sentence**: (1) agent name at the start ("Shadow, ...", "Atlas, ...") -> that agent's lane. (2) Otherwise the *current lane* (the last one used). (3) If the sentence names a different app or kind of work ("ab Chrome pe jao") -> a switch: park the current lane (it stays alive), open or resume the lane of that app.
* **Resume**: a sentence for a parked lane inside 20 minutes -> ask once "Pehle wali File Explorer window mein karun?" (yes/no), then continue there. After 20 minutes the lane closes and the agent says so once.
* **Never ends by itself after an answer.** Ends only on: "end task / bas / khatam / that's all", 20 minutes of silence, or the app window being closed (detected by hwnd).
* Parallel lanes run at the same time; only one lane may use the shared mouse/keyboard at an instant (existing `ui_exclusive` lock).
* Screen: Agents board shows each lane (agent, app, "last step", minutes left); a lane chip on the orb.

### 3.2 Ask-first clarification engine
A table of *ambiguous kinds* with a resolver that enumerates the real candidates from this PC, and a question per language:

| Ambiguous request | Candidates come from | Question (en / roman urdu) |
|---|---|---|
| "open a browser" | installed browsers (registry App Paths) | "Which browser: Chrome, Edge or Firefox?" / "Kaun sa browser kholun: Chrome, Edge ya Firefox?" |
| browser chosen, several profiles | Local State profiles | already built |
| "open email / mail" | Gmail in a browser (+ which), Outlook app, Windows Mail | "Gmail in a browser, Outlook, or Mail app?" |
| "play music" | Spotify app, YouTube in a browser, local files | ask |
| "open notes / editor" | Notepad, Word, VS Code | ask |
| two installed apps match | `winget list` / Start menu | already built for apps |
* The pending question is part of the lane (`awaiting`), answered by voice in any of the 3 languages, by number ("pehla"), or by name.
* The answer can be saved ("hamesha Chrome") into preferences; default is to ask every time, as requested.
* Hard rule: no tool may choose a browser/mail app when more than one exists and the user did not name one.

### 3.3 Controlling everything: layers and a coverage matrix
Order of attack for any request (existing layers, kept): native tool -> Windows UI Automation -> screen vision -> keyboard shortcuts. File Explorer: UIA + `explorer_view` bound to the lane's hwnd. Browser: extension for pages, tab and profile control. Settings: `ms-settings:` pages + registry/COM where verifiable.
Coverage matrix `docs/COVERAGE.md` + `scripts/coverage_live.py`: about 100 operations in 8 groups (apps, windows, files, browser, YouTube, system settings, control panel, device/power, media, mail/chat, coding apps). Each row: spoken examples in 3 languages, tool used, risk, verified-how, last live result (pass / fail / not safe to run).

### 3.4 Coding-app lanes (Forge)
Script for "Claude: nayi chat, project X kholo, prompt ..." = focus window -> new chat shortcut -> open-folder dialog (type the path the user spoke or pick it through Explorer lane) -> verify the project name appears -> click prompt box (OCR hint) -> paste the dictated prompt -> press Enter -> watch until still -> read back. Per-app profile data (hints, shortcuts) kept in `PROFILES`; unmeasured apps say so.

### 3.5 Speed budget (5 to 10 s)
* ack (first word) <= 1.5 s, local path <= 2 s, cloud path <= 8 s, anything longer speaks a progress line.
* Local intent model active in front of the planner for confident, non-risky intents (`may_act`); calibrated threshold; Groq only for the rest.
* Planner: `reasoning_effort=low`, 15 s call timeout, key/model fallback (done). Speech direct to Groq (done).
* Transcription: `large-v3-turbo` first for English/Roman Urdu, `large-v3` for Urdu/Hindi script (language hint from the first words).
* Track p50/p90 in `/voice/latency/stages` after every change; the plan is "done" only when p90 of end-to-end is under 10 s on the checklist.

### 3.6 Languages
English, Roman Urdu, Hindi (Devanagari + spoken), Urdu script. STT vocabulary prompt per language, local model trained with data from many speakers (held-out speakers in the test set), answers spoken in the language of the question.

### 3.7 Safety (kept)
Medium risk: spoken "yes". High risk (delete, uninstall, power, send): on-screen Approve, and the item is read back first. Delete goes to restorable Trash. No password is ever typed. Noise filter before any task is created. Autostart can be switched off from the tray.

## 4. Phases, each with an acceptance test

| # | Phase | Done when |
|---|---|---|
| 1 | **Lanes**: table, `/lanes`, routing, 20 min TTL, park/resume question, end commands, Agents board shows lane + minutes left | Script: "Shadow File Explorer kholo" / "C drive" / "Users" / "Documents" end in ONE Explorer window; 3 minutes later "ek folder banao" still works; "Chrome kholo" parks the lane; "wapas Explorer" asks "same window?"; after 20 min it closes |
| 2 | **Ask-first engine** (browser, mail, music, editor, apps) in 3 languages, optional "always" memory | "browser kholo" asks with the real installed list; "email kholo" asks Gmail / Outlook; no tool ever opens a default browser silently (test fails if it does) |
| 3 | **Coverage matrix** + fixes for the failing rows (settings, control panel, volume, windows, device) | `coverage_live.py` passes >= 90% of the safe rows on this PC; the rest are listed with the reason |
| 4 | **Coding lanes** (Claude, Antigravity) | "Claude mein nayi chat, project <path> kholo, prompt ..." runs end to end on this PC and the result is read back |
| 5 | **Speed**: local model in front of the planner, turbo STT rule, progress lines | p90 end-to-end <= 10 s on the 100-command checklist |
| 6 | **Voice data**: 8+ speakers, retrain, speaker-held-out score, shadow report | new-speaker intent accuracy reported; threshold re-calibrated |
| 7 | **Hardening**: noise/mic health, orb states, crash restart, log of every lane | 1 hour soak on this PC without a stuck lane |

Order: 1 -> 2 -> 3 (these three are what the user will feel) -> 5 -> 4 -> 6 -> 7.

## 5. Paste-ready build prompt

```
You are working in F:\uisoft\fyp-nabiha\AgentDesk_AI (FastAPI backend, React frontend, Windows desktop shell, browser extension). Read
docs/VOICE_AUTOMATION_PLAN.md, docs/STATUS.md and docs/DATASET_GUIDE.md first. Reply to the user in Roman Urdu or English only.

GOAL: the user controls the whole laptop by voice (English, Roman Urdu, Hindi, Urdu). Conversations never end after one answer. Several agents
work at once, each in its own app, and the screen shows which agent does what. Ambiguity is resolved by asking. Every command finishes in 5-10 s.

BUILD, in this order, one phase at a time; after each phase run the acceptance script of that phase, show the real output, fix what fails, update
docs/STATUS.md, and only then start the next:

PHASE 1 - Lanes. New backend/app/orchestration/lanes.py + DB table + GET /lanes. A Lane = {agent, kind, target(hwnd, process, title), state
(folder/url/project), last 20 steps, last_active, status open|parked|closed}. Routing: agent name first; otherwise the current lane; naming another
app parks the current lane and opens/resumes the other one. A lane lives 20 minutes after its last sentence, never ends after one answer, ends on
"end task / bas / khatam", on timeout (say so once), or when its window is gone (check hwnd). Returning to a parked lane asks "same window or a
new one?". Replace the single global task session (orchestration/session.py, session_context.py) by lanes without breaking its tests. File
Explorer navigation ("C drive", "Users", "Documents", "peeche jao", "naya folder") must act on THE LANE'S window handle. Show lanes (agent, app,
minutes left) in the Agents board and the orb caption. Acceptance: scripted run of "Shadow, File Explorer kholo" -> "C drive kholo" -> "Users" ->
"Documents" -> "Chrome kholo" -> "wapas Explorer" -> (asks) "haan" -> "ek folder banao test" with real Windows and one Explorer window.

PHASE 2 - Ask-first. New orchestration/clarify_engine.py: for ambiguous requests (browser, mail, music, editor, several apps) list the REAL
candidates from this PC (installed browsers from the registry, Outlook/Mail app presence, profiles) and ask in the user's language; the question and
its answer are part of the lane; answers by name, number, "pehla/doosra", in 3 languages. No tool may pick a browser or mail client when more than
one exists and none was named (add a test that fails if open_url falls back to a default browser). Optional spoken "hamesha Chrome" saves a preference.

PHASE 3 - Coverage. Create docs/COVERAGE.md (about 100 operations: apps, windows, files, browser, YouTube, settings, control panel, volume,
brightness, wifi/bluetooth, power, media, mail/chat, coding apps) with spoken examples in 3 languages, tool, risk and how it is verified; write
scripts/coverage_live.py that runs the SAFE rows against this PC and records pass/fail; fix failing rows; never run delete/uninstall/power rows
unattended.

PHASE 4 - Coding lanes (Claude, Antigravity): new chat, open the project folder through the app's own dialog, verify the project name, paste the
dictated prompt, press Enter, watch until idle, read back.

PHASE 5 - Speed: put the local ONNX intent model in front of the cloud planner for confident, non-risky intents (Prediction.may_act); keep the
planner for the rest; turbo STT first for English/Roman Urdu; progress line for anything over 3 s. Measure with /voice/latency/stages; target p90
under 10 s on a 100-command checklist.

PHASE 6 - Voice data: collect sessions per speaker (ml/collect_history.py --speaker), retrain, report new-speaker accuracy, recalibrate.

PHASE 7 - Hardening and a 1-hour soak.

RULES: never type passwords; delete -> Trash; uninstall/delete/power/send need on-screen approval after reading the item back; do not commit
unless asked; tests for every new module (pytest, backend/tests); rebuild the frontend (npm run build) when it changes; restart the backend
(kill launch.py and run_server.py first, the old process keeps old code) before live checks; report honestly what was NOT verified.
```

## 6. Decisions needed from the user before Phase 1
1. Lane life: 20 minutes of silence (as said). Ask "end this task?" at 15 minutes, or silent close at 20?
2. "Always use Chrome" memory: allowed (opt-in), or ask every single time?
3. Wake behaviour: always listening with the junk filter (now), or "Shadow" / agent names as the call word so room noise is ignored?
4. Which email: Gmail in browser, Outlook app, Windows Mail, or all three?
