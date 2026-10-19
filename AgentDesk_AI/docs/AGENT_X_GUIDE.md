# Agent X AI conversational controls

The frontend now displays Agent X AI. The existing configured provider remains Groq (GROQ_API_KEY), not xAI Grok. No API keys were changed.

## Start (normal use)

Double-click **START_AGENT_X.cmd** in the workspace root. It starts the backend in the background, waits until the API and built frontend both respond, then opens http://127.0.0.1:8000.

The UI and backend share this address, so normal use needs only one server and no separate Vite terminal. Launching again reuses the healthy server instead of creating a duplicate. A background supervisor restarts a crashed backend up to three times; errors are kept in AgentDesk_AI/logs/backend.log and launcher.log. Do not run an older backend separately on port 8000. If another app occupies that port the launcher reports it and does not terminate it.

After editing frontend sources, run `npm.cmd run build` inside frontend. After backend code changes, stop the existing project server/supervisor before starting the launcher again. Closing the browser does not stop the backend. Windows restart stops the processes; double-click the launcher to start again.

## Developer mode

For frontend development, run the backend with `run_server.py` and `npm.cmd run dev` inside frontend. Vite at http://127.0.0.1:5173 proxies /health, /config, /tasks and /tools to the backend at port 8000. Frontend requests always use the page's own origin; both localhost and 127.0.0.1 development origins are allowed. Connection status refreshes every five seconds and when the page regains focus. PC commands are never automatically retried.

## Try a conversation

- Say/type: "Lower brightness" or "Volume up". Brightness and volume are reversible settings and run without a separate popup. Bluetooth changes still request approval.
- "Open VS Code" or "Close WhatsApp" uses existing application discovery and window controls. A close can stop at an unsaved-work prompt.
- "Find my lecture folder" returns matching full paths from configured allowed directories. With multiple matches, select a path or ask to open a candidate for inspection, then continue the original copy/move/rename/delete request.
- "No, the folder is at D:\College\lecture" provides a correction. A correction during pending approval cancels the old proposal and replans it.
- "Delete this folder including its contents" produces a popup with the path and include_contents flag. Non-empty folder deletion is limited to configured allowed directories and moves the folder to internal restorable Trash. Ask to list Trash and restore an item to recover it.
- "Download VS Code" searches WinGet, checks the selected package, and requests approval before downloading. The result includes the actual files. The installer is never run automatically.
- "Download WhatsApp Desktop" can search the Microsoft Store source. Store download availability and sign-in requirements depend on the package; failures are reported instead of claiming a successful download.
- "Write an email to user@example.com about tomorrow's lecture" prepares an email draft in the default mail application. Review it there and use Send or Cancel yourself. The assistant is instructed not to send through desktop automation.

## Confirmations and voice

The popup shows the exact tool arguments, including source/destination and email content where relevant. Use Yes, do it / Cancel, or type/speak a short affirmative/negative answer. English, Roman Urdu, Hindi and Urdu confirmations are recognized. The reply API is bound to a specific pending task ID; a reply to a completed/cancelled task cannot re-execute it. Edited paths go through a new proposal.

Enable the microphone, select the appropriate language, and speak. Browser speech recognition needs microphone permission and internet. Voice replies resume listening after the assistant speaks, including while waiting for approval. Use exact paths when bounded folder search is incomplete (5000 directory visits, six levels, up to 30 displayed candidates).

## Requirements and verification

Live natural-language planning requires the configured Groq model and a working API key/network. Windows display/audio support requires the packages in backend/requirements.txt and compatible hardware/drivers. Email composition requires a configured default mail application. Download tools require Microsoft App Installer/WinGet. Some package sources need their terms accepted interactively before noninteractive commands work.

WinGet download implementation follows Microsoft's documentation: https://learn.microsoft.com/windows/package-manager/winget/download

Automated verification: 120 backend tests passed, one optional live-provider test skipped; the TypeScript/Vite production build passed. New tests cover ambiguous folders, Unicode names, Hindi/Urdu confirmations, cancellation, exact package download without executing installers, and non-empty-folder Trash/restore. Tests mock Windows/network side effects; live hardware, microphone, Store downloads and email clients still need a manual check on the target PC.

## API quota handling

See [API reliability and backup setup](AI_RELIABILITY.md). Groq remains primary, exact simple commands run locally, and rate-limited tasks can resume without replaying completed actions.

## Local agent pipeline

See [local agent commands and behavior](LOCAL_AGENT.md). Everyday PC commands use the local engine; free-form cloud reasoning is opt-in by default.
