Agent X AI / AgentDesk AI - Windows install (version in VERSION file)
===================================================================

Requirements: Windows 10/11, Python 3.12 (https://www.python.org/downloads/), internet for the
one-time dependency install. Node.js is NOT needed (the web UI is prebuilt).

1. Extract this zip somewhere you own, e.g. C:\Users\<you>\AgentDesk-AI  (not Program Files).
2. Double-click INSTALL.cmd. It creates a private .venv inside this folder and installs pinned
   packages. It changes nothing outside the folder (no registry, PATH, Wi-Fi or Bluetooth).
3. Double-click START_AGENT_X.cmd. Your browser opens the app. Local PC commands work immediately.
4. Optional cloud AI: put your own key in AgentDesk_AI\backend\.env (GROQ_API_KEY=...). Never share it.
5. Optional browser tab control: see AgentDesk_AI\docs\BROWSER_CONTROLS.md (extension + pairing).

Where things are stored
- Task history: AgentDesk_AI\backend\agentdesk.db
- Logs and the access token: %LOCALAPPDATA%\AgentDesk\ (logs\agentdesk.log, api_token)
- To uninstall: delete this folder and %LOCALAPPDATA%\AgentDesk.

Safety summary: the app asks before changing files, high-risk actions need their own approval,
changes to files can be undone from the app, and nothing is sent to a cloud service unless you
configure a key and ask for AI reasoning ("AI: ..."). It is a prototype: read
AgentDesk_AI\docs\audit\FINAL_ACCEPTANCE_AND_SECURITY_REPORT.md for what was and was not tested.

Troubleshooting: AgentDesk_AI\docs\TROUBLESHOOTING.md
