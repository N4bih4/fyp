# FYP demonstration checklist

A 10-minute live demo flow. Rehearse once end-to-end before the examiners arrive.
Backend on `127.0.0.1:8000`, frontend on `localhost:5173`, mock AI mode unless
you explicitly enable OpenAI.

## Before the demo

- [ ] `scripts\verify_windows.py --api` → all checks green
- [ ] `AGENTDESK_ALLOWED_DIRECTORIES` points at a demo folder; create it
- [ ] Chrome installed (for the launch step)
- [ ] Close unrelated apps; examiners will see your screen
- [ ] Frontend badge shows the expected AI mode

## Demo flow (~10 min)

1. **Intro (1 min)** — "AgentDesk AI turns natural-language commands into
   planned, permission-checked, verified computer operations. Pipeline:
   understand → plan → validate → permission check → approval → execute →
   verify → report. The AI only emits structured tool calls — never raw
   shell commands."
2. **Low risk (1 min)** — `Open Chrome`. Point out: auto-approved, low risk,
   launches for real.
3. **Medium risk + approval (2 min)** — `Create a folder called FYP in Documents`.
   Show the plan preview, amber risk badge, Approve → Execute, green
   verification (`folder exists: True`). Open Explorer to prove it's real.
4. **High risk + rejection (2 min)** — `Delete the file <path>`.
   Show the red badge and explicit-approval requirement. Then **Reject** it and
   show the file still exists. (Or approve it on a disposable file.)
5. **Security (2 min)** — `Show the result of the previous task`; mention the
   blocked attacks: path traversal, zip-slip, no-overwrite policy, and that
   finished tasks never re-execute. Reference `docs/SECURITY.md`.
6. **Architecture + AI (1.5 min)** — provider abstraction (`app/ai/base.py`),
   mock vs OpenAI, structured JSON validated by Pydantic, secrets only in
   `backend/.env`, cost notes in `docs/DEPLOYMENT.md`.
7. **Tests (0.5 min)** — `python -m pytest tests/ -q` → 42 passed (run it live
   or show the earlier output).

## Likely examiner questions

- "What stops the AI from deleting everything?" → Risk tiers + explicit
  approval + allowed directories + backend-side validation independent of the
  model. Demo the traversal block.
- "What happens when the AI is wrong?" → Plan preview before execution,
  per-action verification, honest failure reporting, no blind retries.
- "Why mock mode?" → Deterministic, free, offline — tests never incur API
  costs; OpenAI is a drop-in provider swap.
- "What would you add next?" → Voice input, deeper UI automation, packaged
  `.exe` distribution (spec already in repo), per-user auth for network use.

## If something breaks live

Stay calm, narrate the failure honestly ("the tool reported X, verification
failed, so it stopped instead of continuing blindly") — that **is** the
system working as designed. Fall back to the `verify_windows.py` output and
the task history in the UI.
