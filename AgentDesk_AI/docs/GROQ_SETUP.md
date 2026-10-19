# Groq setup guide (safe)

Groq is the primary AI provider for AgentDesk AI: a real LLM with function
calling. Pricing, quotas, and model availability can change; check Groq's
current documentation and your account limits before using it.

## 1. Get a free API key

1. Go to https://console.groq.com/keys and sign up / sign in.
2. Create an API key (starts with `gsk_`).
3. **Never** paste it into chat, screenshots, frontend code, or Git.

Each model turn may incur provider usage. Multi-step tasks may make multiple
turns, bounded by `AGENT_MAX_STEPS`; transient rate-limit retries honor the
provider's reset headers when available and stop rather than retrying early
when the reset is more than 15 seconds away.
Check https://console.groq.com/settings/limits and current pricing for your
account. If a rate limit is exceeded the app reports it instead of retrying
forever.

## 2. Configure the backend

In `backend/.env` (copy from the repo-root `.env.example`):

```
AI_PROVIDER=groq
AI_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=gsk_paste-your-key-here
AGENT_MAX_STEPS=10
```

Model choice: check https://console.groq.com/docs/models because IDs and access
change. The current default, `openai/gpt-oss-120b`, was verified with a live
tool-free request. Select a model that supports tool calling for desktop tasks.

Restart the backend after editing `.env`.

## 3. Verify without spending anything

```powershell
# config reports readiness WITHOUT exposing the key:
curl http://127.0.0.1:8000/config/status
# expect: "ai_provider":"groq", "groq_configured":true, "mock_mode":false
```

The UI header badge reads the same endpoint and shows **"groq connected"**.

## 4. Opt-in live test (exactly one cheap call)

Only run this when you are ready to spend a few dozen tokens:

```powershell
$env:GROQ_API_KEY="gsk_paste-your-key-here"
$env:AGENTDESK_LIVE_GROQ="1"
.\.venv\Scripts\python -m pytest tests/test_groq_live.py -v
```

It is skipped by default. Never claim it passed unless you actually ran it.

## 5. How the agent loop works

1. You submit a command → the model proposes **one tool call at a time**.
2. The backend validates the tool name and arguments **independently** of the model.
3. The permission engine checks risk: **low** runs immediately, **medium/high**
   pause the task for your approval in the UI.
4. You approve → Execute (or the loop continues) → the real tool result goes
   **back to the model** for the next reasoning step.
5. Installed applications can be launched by name; existing windows are reused
   when possible. The `control_desktop` tool can inspect the active window and
   perform up to eight bounded keyboard/mouse actions. Input is automatic only
   when the user's command names the target app and requested action; actions
   targeting unnamed/mismatched windows still need approval. Closing a window
   also requires explicit close wording and is verified. It uses screen
   coordinates and cannot guarantee support for every or protected window.
6. The loop ends when the model answers in plain text, or after
   `AGENT_MAX_STEPS` tool steps (then the task fails with a clear message).

If Groq is unreachable, misconfigured, or rate-limited, the task **fails with
a clear error** — the app never silently swaps in mock responses. Mock mode
still exists for offline tests: set `AI_PROVIDER=mock` explicitly.

## 6. Troubleshooting

| Symptom | Meaning / fix |
|---|---|
| Task fails: "GROQ_API_KEY is not set" | Add the key to `backend/.env`, restart the server |
| Task fails: "Groq rejected the API key" | Key is wrong/revoked — regenerate at console.groq.com/keys |
| Task fails: model "not available" | `AI_MODEL` ID changed — pick one from console.groq.com/docs/models |
| Task fails: "rate limit exceeded" | Wait for the retry interval shown (if provided), check the Groq limits dashboard, and retry after the request/token quota resets |
| UI badge says "Mock AI mode" | `AI_PROVIDER` is `mock` in `.env` — set it to `groq` and restart |
