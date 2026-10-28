# Phase 3 Completion Report: planning, clarification, provider errors

Date: 2026-10-26. Nothing committed.

## Blocker resolved (Phase 1 and 2 carry-over)
`groq` and `openai` were installed in a Python 3.12 venv (`backend/.venv-p3`, git-ignored) after retrying with long timeouts (the network ran at roughly 9 kB/s). Full suite on **Python 3.12.x with SDKs: 337 passed, 1 skipped (opt-in live Groq test), 0 failed.** This means the 10 agent-loop tests, `test_groq_provider.py` and the 2 resilience tests now executed and pass against the Phase 1 and 2 changes, including the strict state machine. Python 3.14 (no SDKs): 311 passed, 13 skipped.
Not installed in the 3.12 venv: `pyautogui`, `pycaw`, `screen-brightness-control`, `winsdk`. Tests pass without them because hardware paths are mocked or skipped; real hardware behaviour remains NOT VERIFIED.

## Defects found and fixed
- **Silent argument corruption (new, High):** `GroqProvider._normalize` replaced malformed or non-object tool-call JSON with `{}`. A tool whose arguments all have defaults could then execute an action the model never specified. Calls are now flagged `invalid_arguments`, and the executor rejects them without creating an action, telling the model to retry.
- **Truncated tool calls:** a response with `finish_reason=length` and tool calls now raises `AIError` (it was handled only in the backup provider).
- **Prompt privacy (B-09):** prior-task context sent to the model now omits file contents and other long text (`content`, `text`, `body`, `stdout`, ...), bounds lists to 10 items, strings to 300 characters and per-task context to 2000 characters. Paths and ids are kept so "yes, that one" still resolves.

## Provider error matrix (stub-SDK tests)
Auth rejected and model-not-found map to `AIConfigError`; timeout, connection, generic API and bad-request errors map to `AIError`; rate limit maps to the recoverable `AIRateLimitError` with `retry-after`; error text never contains the API key; a missing key fails loudly with no mock fallback. These tests use a stub `groq` module, so they verify our mapping, not the real SDK's exception classes. The real-SDK tests in `test_groq_provider.py` also pass on the 3.12 venv.

## Dependencies (B-14)
`backend/requirements.lock.txt` records the versions the 337-test run used (Python 3.12, no hardware libs). It is a record of a verified set, not yet the file the installer uses.

## NOT VERIFIED / open
- No live call to Groq, Gemini or OpenAI was made; model IDs in `.env.example` are unchecked.
- Natural-language understanding quality (Urdu / Hindi / Roman Urdu, multi-turn clarification) was not extended this phase; existing rule-based tests pass but coverage is limited to tested patterns. No new clarification features were added.
- The explicit-`AI:` cloud opt-in routing was not changed or re-reviewed.
- Hardware tools on a real device.
