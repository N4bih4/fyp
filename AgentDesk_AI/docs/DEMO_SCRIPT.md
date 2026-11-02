# Demo script — Agent X 0.2.0 (12 minutes)

Goal: show that the assistant understands four languages, always shows what it will do, and only says
"done" after checking the real PC. Rehearse once. Replaces nothing in DEMO_CHECKLIST.md (older 0.1 flow).

## Setup (before the audience arrives)
- Fresh profile so onboarding shows: delete `%LOCALAPPDATA%\AgentDesk\agentdesk.db` (back it up first).
- Start `START_AGENT_X_DESKTOP.cmd` (or `START_AGENT_X.cmd`). Microphone allowed. Spotify or a YouTube song playing, then paused.
- Memory page: add "Ahmed: <your own number>". Browser extension paired (badge ON).
- Close anything private on screen. Have `docs\pilot\2026-10-31-pilot-linux.md` and the traceability matrix open in a tab.

## Flow

| # | Minute | Do / say | Point out |
|---|---|---|---|
| 1 | 0:00 | Show the orb, then open the panel | Always-on-top orb; states animate (Ready) |
| 2 | 0:30 | Onboarding: pick English, Next, Next, **Start**; say "Create a folder called Demo in Documents" | Live transcript; amber card shows the exact path; nothing exists yet |
| 3 | 1:30 | Press **Approve** | Orb "Checking the result" → completed; open File Explorer: folder is there |
| 4 | 2:00 | Press **Undo changes** | Folder disappears, undo verified |
| 5 | 2:30 | Say "volume 40 kar do", then "thora aur" | Roman Urdu; follow-up; read-back value matches the Windows slider |
| 6 | 3:30 | Say "notepad kholo", then "isay band karo" | "it" resolved from conversation memory |
| 7 | 4:30 | Say "اگلا گانا" (Urdu) then "गाना रोक दो" (Hindi) | Media keys; verified from Windows media session (track title / paused) |
| 8 | 5:30 | Create `Documents\notes.txt`; say "delete file notes.txt" | **Red** card; say "haan" → refused ("High risk needs a click"); press **Reject** with Esc |
| 9 | 6:30 | Say it again and click **Approve**, then **Undo** | File restored from Trash |
| 10 | 7:30 | Say "ahmed ko whatsapp pe message bhejo ke demo chal raha hai" | Medium card shows contact + message + "not sent"; WhatsApp opens pre-filled; close without sending |
| 11 | 8:30 | Say "youtube band kar do" | Exact tab closed through the extension; other tabs untouched |
| 12 | 9:00 | Settings: Approval policy → Strict; say "notepad kholo" | Even low risk now waits; switch back |
| 13 | 9:30 | Open `http://127.0.0.1:8000/metrics/tasks.csv` (or the pilot CSV) | One row per task: timings, approvals, verified actions — no command text |
| 14 | 10:00 | Show the traceability matrix | Measured vs not measured, honestly |
| 15 | 11:00 | Questions | |

## If something fails on stage
- Mic not hearing: type the same command (press `/`). Voice is browser speech recognition and needs internet.
- WhatsApp/winget/media step fails: say so — these were unit-tested but first live runs happen on this PC
  (see INTEGRATIONS.md); show the verifier message as evidence of honest failure.
- Never demo Wi-Fi/Bluetooth off, installs, or typing into other apps live.

## Part 2 — control of every app (upgrade U1–U7, +10 minutes)

Setup: cloud answers ON, Groq key set, `python backend\scripts\vision_testapp.py %TEMP%\state.json` ready (a canvas app that Windows accessibility cannot read),
a Gmail/Outlook test mailbox connected (Settings → Email), browser extension 1.2.0 paired, a YouTube video open.

| # | Do / say | Point out |
|---|---|---|
| 16 | "open notpad" | Mis-heard name resolved; say "no I meant Notepad" once and show it is remembered |
| 17 | "In Calculator click seven, plus, eight, equals" | Layer 2: each click approved, result 15 read back from the real control |
| 18 | "open a terminal in Documents and run git status" | Live PowerShell window; output read back; then "run format c:" is refused |
| 19 | "pause YouTube", "speed 1.5" | Verified from the page, not assumed |
| 20 | "write an email to <test address> saying the demo works" | Draft, read-back, "change the last line", **"yes, send it"**; then it confirms from the Sent folder |
| 21 | Start the canvas test app. "click Start", "click Add plus ten" | Spoken notice "needs me to look at the screen"; show a numbered picture from `docs\eval\u7_images`; the score really changes |
| 22 | "click the Unicorn button" | It refuses instead of guessing |
| 23 | Settings → untick "Let the assistant look at app windows"; repeat step 21 | Refused, no picture sent |
| 24 | Say "stop" during a task | Kill switch |
| 25 | Show `docs\FINAL_REPORT_U8.md` | Measured numbers per milestone, including what failed |

Do not demo: sending to a real contact, payments, typing into a password field.
