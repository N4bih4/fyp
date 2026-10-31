# Controlled pilot checklist

I (the assistant) cannot run a pilot with real users and could not exercise real devices. This is the list a person must run on the target PC, in order. Do not skip the safety notes.

**Before you start:** use a scratch Windows user or a PC you can afford to lose settings on; close important work; have the Wi-Fi/Bluetooth recovery path ready (you know how to re-enable them from Windows Settings). Use your own Groq key only if you want to test cloud AI.

## A. Install (about 10 minutes)
- [ ] Download `AgentDesk-AI-0.2.0-win.zip` and compare its SHA-256 with the `.sha256` file.
- [ ] Extract to `C:\Users\<you>\AgentDesk-AI`. Run `INSTALL.cmd`. Expect "Self-check passed" and "Installed".
- [ ] Run `START_AGENT_X.cmd`. The browser opens the app (the address bar loses the `#token=` part after load).
- [ ] Run INSTALL.cmd a second time. Expect it to reuse the environment and still succeed.
- [ ] Optional: delete the extracted folder and `%LOCALAPPDATA%\AgentDesk` afterwards to confirm a clean uninstall leaves nothing else.

## B. Core safety (use a scratch folder under Documents)
- [ ] "Create a folder called pilot_test in Documents": the dialog shows the exact path; nothing exists until you press Yes; folder appears; task says verified.
- [ ] Press **Undo changes**: folder disappears; the screen says undone and verified.
- [ ] Create a text file with content, then overwrite it with a different content and Undo: the original text returns.
- [ ] Delete a disposable file, confirm in the dialog, then Undo: the file returns from Trash.
- [ ] Press Cancel on a pending action: nothing changes.
- [ ] Reload the page mid-way: history still lists tasks.

## C. Real devices (only reads and reversible steps; note the original values first)
- [ ] "get volume": the number matches the Windows volume slider.
- [ ] Set volume to a value, confirm via slider, set it back.
- [ ] Brightness: same (laptop panels only).
- [ ] Open and close Notepad by command; confirm only that window closes.
- [ ] **Wi-Fi and Bluetooth: do NOT test unless you accept losing connectivity briefly and can restore it by hand.** These were deliberately never exercised during development.
- [ ] Do not test typing into other applications on a machine with unsaved work.

## D. Cloud AI (optional, costs money on your key)
- [ ] Put your own key in `AgentDesk_AI\backend\.env`; restart.
- [ ] "AI: summarise what you can do": answer arrives; no key appears in any screen or in `%LOCALAPPDATA%\AgentDesk\logs\agentdesk.log`.
- [ ] Disconnect the network and try again: a clear error, no crash, task not left running.

## E. Browser extension (optional)
- [ ] Follow BROWSER_CONTROLS.md: load the unpacked extension, open the setup page from the app link, see "Paired", badge turns ON.
- [ ] "list tabs", close one named tab, pause/resume a YouTube video; verify unrelated tabs are untouched.

## F. Reliability
- [ ] Start a task, then close the console window of the server mid-run, restart: the task shows failed/interrupted, not completed; check the real file state yourself.
- [ ] Voice: hands-free command works; the assistant's own speech does not trigger commands.

## What to report back
For each unchecked or failed item: what you typed, what you saw, the time (to find the line in the log). Do not send the `.env`, the token file or screenshots showing keys.

## Go / no-go
Release only if A and B pass fully, C passes for the controls you will actually offer, and nothing in the residual-risk register of FINAL_ACCEPTANCE_AND_SECURITY_REPORT.md is unacceptable for your users.
