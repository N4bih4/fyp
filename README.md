# Agent X AI / AgentDesk AI

Conversational Windows desktop assistant with a FastAPI backend, React frontend, local command routing, and optional Groq reasoning.

Project source: [AgentDesk_AI](AgentDesk_AI). Start script: `START_AGENT_X.cmd`.

## Setup

1. Install Python 3.11+ and Node.js.
2. In `AgentDesk_AI/backend`, create `.venv` with `python -m venv .venv`, then run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
3. Configure the backend local environment following [Windows setup](AgentDesk_AI/docs/SETUP_WINDOWS.md). Keep real keys out of Git.
4. In `AgentDesk_AI/frontend`, run `npm.cmd ci` and `npm.cmd run build`.
5. Run `START_AGENT_X.cmd` from the repository root. Open http://127.0.0.1:8000/.
6. Browser tab/media controls require the supplied extension in the intended Chrome profile; reload it after extension source updates.

## Current verification and limitations

Read the [feature audit](AgentDesk_AI/docs/FEATURE_AUDIT.md), [roadmap](AgentDesk_AI/docs/IMPLEMENTATION_ROADMAP.md), and [troubleshooting](AgentDesk_AI/docs/TROUBLESHOOTING.md). Implementation, mocked tests, and actual Windows verification are distinguished there. The complete conversational product is still under development.

## Tests

Run `python -m pytest tests -q` in the backend with its test dependencies installed. Frontend voice helpers: `node --test voice.test.mjs` in the frontend. Extension mocks: `node AgentDesk_AI/browser-extension/tests/test_controls.cjs` from the repository root.
