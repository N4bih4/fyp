# Usability test: "a new user gives a voice command and approves it in under 3 minutes"

The automated test (`frontend/e2e/new_user.test.mjs`) walks the same path with a fake microphone in about 3 s.
It proves the path works; it does **not** prove that a person finds it. Run this with 5 people who have never used AgentDesk.

## Setup (per participant)
1. Fresh profile: delete `%LOCALAPPDATA%\AgentDesk\agentdesk.db` (or use a new Windows user) so onboarding appears.
2. Start `START_AGENT_X_DESKTOP.cmd` (or `START_AGENT_X.cmd` for the browser version). Wait until the panel shows.
3. Microphone plugged in; Chrome/Edge WebView allowed to ask for microphone permission.

## Task given to the participant (read aloud, no other help)
"This assistant can do things on the computer. Ask it, by voice, to create a folder called Demo in your Documents folder."

## Measure
- Start the timer when the panel is visible; stop when the task shows **completed** and `Documents\Demo` exists.
- Note every point where the person hesitated > 10 s, asked for help, or did something unintended.
- Pass: 4 of 5 people under 3:00 with no help. Record times in the table.

| # | language | time (m:s) | help needed? | notes |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
