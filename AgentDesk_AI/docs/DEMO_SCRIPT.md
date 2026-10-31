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
