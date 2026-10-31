# AgentDesk AI — STATUS

Single source of truth for "what is done". Updated at the end of every session.
Older evidence: `FEATURE_AUDIT.md`, `audit/FEATURE_TRACEABILITY_MATRIX.md`,
`audit/FINAL_ACCEPTANCE_AND_SECURITY_REPORT.md`, `audit/phases/PHASE_*_COMPLETION.md`.

## Session log

### 2026-10-31 — Session 3: Phase 15 NATURAL-LANGUAGE COMMAND MODEL

Phase 14 was skipped as a separate step; its planner pieces (PlannerProvider, Groq structured outputs, fallback chain) are delivered here.

**Done** (package lives in `backend/app/nlu/`, next to `app/ai/`, so it imports like the rest of the app)
- `schema.py`: plan schema v2 (`NLUPlan`: intent enum, language, confidence, needs_clarification, clarifying_question, steps[tool,args,depends_on,expected_outcome], reply). `plan_json_schema(registry)` builds the strict JSON schema: one step variant per registered tool (tool enum generated from the registry), every property required, `additionalProperties:false` everywhere, optional values nullable, unsupported keywords stripped. `validate_plan()` = the single server-side gate for every provider: unknown tool, unknown/invalid argument (incl. `auto_approve`), bad `depends_on`, bad `$N` step reference, path outside allowed roots -> rejected with a reason; risk from `tool.risk_for_args`.
- `normalizer.py`: language detection (script + Roman Urdu markers), number words in en/roman_ur/ur/hi -> digits, shared multilingual lexicon -> canonical tokens, rapidfuzz typo correction (ASCII only, cutoff 86, never on paths/URLs/e-mails), nukta/NFKC handling.
- `local_matcher.py`: ordered rules over canonical tokens (unsupported, chat, e-mail, settings pages, device settings, follow-ups, browser/media/search, websites, screenshot/trash/packages, explicit paths, file ops with find_paths + `$0`, apps, clarification). Confidence 0.95 minus penalties for typos and unexplained words; unknown -> 0. Negated commands are never matched.
- `memory.py`: last 10 turns, last results, `last_target` only from the immediately preceding successful turn, ordinals into the last result list, JSON prompt view.
- `planner.py`: `PlannerProvider.plan(context) -> PlanResult`; `GroqPlanner` (one call, `response_format` json_schema strict, no tools/streaming, gpt-oss-120b -> gpt-oss-20b, via `GroqClient`), `OpenAICompatiblePlanner` (OpenAI; Gemini via its OpenAI endpoint) with the same schema and validator, `FallbackPlanner`, `LocalFirstPlanner` (Groq only below 0.85), usage per plan, `planner_from_settings()`.
- `prompts/system.md` (role, rules 1-8, conventions, tool catalogue) + `prompts/examples.jsonl` (11 few-shot plans: en, roman_ur, ur, hi, multi-step, follow-up, ordinal, ambiguous -> question, unsupported, adversarial "don't ask"). None of them is in the eval set (test enforces it).
- `tests/nlu_eval/commands.jsonl` (300: en 92, roman_ur 88, ur 60, hi 60; dev 201 / holdout 99), committed before the matcher. `tests/nlu_eval/paraphrases.jsonl` (40 independent probes).
- `scripts/eval_nlu.py`: modes local / pipeline / llm; accuracy per language and split, invented tools, approval bypasses (approval tier of the predicted plan lower than expected for the same intent, or approval-like argument), language detection, paraphrase probe; writes `docs/eval/nlu_<mode>_<split>.md/.json`.
- `rapidfuzz` added to `requirements.txt` and `requirements.lock.txt` (3.14.6; not yet installed/verified on the Windows PC).

**Tested how (Linux container, Python 3.13)**
- `python -m pytest tests -q` -> **595 passed, 3 skipped, 0 failed** (skips = Groq live tests, no key). New `tests/test_nlu.py`: 43 tests (strict-schema rules on every object, validator rejections, path check, normaliser, matcher, adversarial delete stays HIGH risk, memory, planners with fake Groq/Gemini clients incl. 120b->20b fallback and backup provider, prompt contents, dataset validity, **Gate G3 as a regression test**).
- `python scripts/eval_nlu.py` -> **Gate G3 PASS**: intent+tool 99.3%, exact args 99.3%, 0 invented tools, 0 approval bypasses (holdout first run 100.0% / 99.0%). Paraphrase probe 20/40 correct, 20 deferred, **0 confidently wrong**. Report: `docs/eval/nlu_local_all.md`, caveats in `docs/eval/README.md`.

**What is left**
- Run `python scripts/eval_nlu.py --mode pipeline` with `GROQ_API_KEY` (verifies Groq accepts the strict schema, measures LLM accuracy and latency).
- **Not wired into the executor yet.** `start_task` still uses the existing local agent + Groq tool-calling loop. Wiring `LocalFirstPlanner` in (resolving `$0` via find_paths, feeding memory from task history) changes the live command path — needs your go-ahead (see open decision 1).
- Real-user transcripts as a third eval split.

**Known issues**
- Same author for data and matcher: in-set numbers are optimistic; the probe shows ~50% local coverage of unseen phrasing.
- Groq strict-schema compatibility (anyOf of 29 variants, `type: [x, "null"]`) is unverified live.
- Push to GitHub still fails with 403; all commits are local.

### 2026-10-31 — Session 2: Phase 13 STABILISE

**Done**
- `backend/app/ai/groq_client.py` — `GroqClient`: one client for chat, STT (`whisper-large-v3-turbo` -> `whisper-large-v3`) and TTS (`canopylabs/orpheus-v1-english`, WAV).
  Explicit per-request timeout; 429 / 5xx / connection errors retried with exponential backoff (1 s, 2 s, +10% jitter) honouring `Retry-After`, max 2 retries; a Retry-After above 15 s is not waited out (raises `AIRateLimitError`). Timeouts, auth (401/403) and unknown model (404) are never retried. Thread-safe `UsageCounter` per kind (calls, succeeded, failed, retries, rate_limited, tokens, audio seconds, TTS chars). One `groq_call` log event per attempt with kind/model/status/HTTP status/duration only — no prompt, transcript, spoken text or key; error text goes through `redact`. STT passes `language` and `prompt` (known names). `get_groq_client()` gives one shared instance.
  Note: the brief said `backend/ai/`; the package is `backend/app/ai/`, so the file lives there.
- New settings: `GROQ_STT_MODEL`, `GROQ_STT_FALLBACK_MODEL`, `GROQ_TTS_MODEL`, `GROQ_TTS_VOICE` (`config.py`, `.env.example`).
- `backend/scripts/live_check.py` — runs every registered tool once (29 tools) in a temp sandbox that is the only allowed/discovery directory, calls `validate_args -> execute -> verify`, then an **independent** check of real state (disk content, zip members, trash records, PNG header, PID alive...). PASS only when tool, `verify()` and the independent check all agree. Categories: `sandbox` + `read` (default), `gui` (`--gui`), `network` (`--network`). Never runs setters, clicks/typing, tab closing or WinGet download. Statuses PASS / FAIL / BLOCKED (missing prerequisite) / SKIP. Exit 1 on any FAIL or on a registered tool without a probe.
- Existing `GroqProvider` not yet switched to `GroqClient` (Phase 14 builds the planner on it).

**Tested how (Linux cloud container, Python 3.13, Node 22)**
- Backend: `python -m pytest tests -q` -> **552 passed, 3 skipped, 0 failed**. Skips: 2 new live Groq smoke tests + old opt-in Groq test (no `GROQ_API_KEY` here).
- New: `tests/test_groq_client.py` (16, fake SDK: backoff timings, Retry-After, long Retry-After, 5xx retry, no retry on auth/timeout, real `groq.RateLimitError`, STT language/prompt + fallback, TTS, usage, log redaction), `tests/test_groq_client_live.py` (chat + TTS->STT round trip, skipped without key), `tests/test_live_check.py` (4: probe for every tool, no dangerous probe, sandbox probes really pass, missing probe = FAIL).
- Frontend: `npm ci && npm run build` (tsc + vite) -> pass. `node --test voice.test.mjs` -> 4/4. Extension: `test_controls.cjs`, `test_pairing.cjs` -> pass.
- `python scripts/live_check.py --gui --network` -> **29 tools reported: 15 PASS, 0 FAIL, 14 BLOCKED, 0 SKIP**. All 15 file tools PASS with disk evidence. BLOCKED because this is headless Linux: system setting read, desktop inspect, WinGet, Settings, all GUI launches; browser extension not connected to the script process; no direct DNS for the download.

**What is left**
- Run `python scripts/live_check.py --gui --network` on the Windows PC and paste the table here (the 14 BLOCKED rows need it).
- Run the live smoke test with a real key: `$env:GROQ_API_KEY=...; python -m pytest tests/test_groq_client_live.py -v`.
- `control_browser` probe can only reach the extension through the running server; add an `--api` mode later.

**Known issues**
- GUI probes verify "launch requested / PID alive", not the visible window (Phase 17 verifiers).
- Probe timeout uses a thread that cannot be killed (same limit as R-08; Phase 17 worker process).
- Push to GitHub is failing with 403 (Claude GitHub App access to `N4bih4/fyp`); commits are local until access is fixed.

### 2026-10-31 — Session 1: baseline and plan (no code changed)

**Done**
- Read README, feature audit, traceability matrix (R-01..R-33), final acceptance report, phase 0-12 reports, `ai/` and `tools/` layout.
- Created this file and the phase plan below.

**Tested how**
- Full backend suite on Linux (Python 3.13, cloud container, no Windows SDKs):
  `python -m pytest tests -q` -> **529 passed, 4 skipped, 0 failed** (skips: live Groq + Windows-SDK tests).
  Windows reference (2026-10-28, Python 3.12, pinned deps): 532 passed, 1 skipped.

**Known issues / decisions needed** — see "Open decisions" below.

## Baseline vs. target architecture

| Area | Today (in repo) | Target (product brief) | Gap |
|---|---|---|---|
| Plan model | `ai/base.py` `Plan{actions[{tool,args,rationale}], note}` | `Plan{intent, language, confidence, needs_clarification, clarifying_question, steps[{tool,args,depends_on,expected_outcome}], reply}` | New schema + adapter so executor keeps working |
| Provider interface | `AIProvider.generate_plan(command, tool_descriptions)` | `PlannerProvider.plan(context) -> Plan` | Context object (desktop, memory, profile) |
| Groq | Multi-turn **tool-calling** agent loop (`groq_provider.py`, `executor.py`) | **Single** call, `response_format=json_schema, strict=true`, `gpt-oss-120b` -> `gpt-oss-20b` -> Gemini/OpenAI | Rewrite of the call path; agent loop retired or kept behind flag |
| Tool enum | Registry validates names after the fact | Enum generated from registry at startup inside the JSON schema | Schema builder |
| Local fast path | Regex/normaliser per domain (`speech_commands`, `command_language`, ...) | Normaliser + rapidfuzz, confidence score, Groq only if < 0.85 | Confidence scoring, rapidfuzz |
| Memory | Recent-task memory, local workflow state | Last 10 turns, resolved references, opt-in profile | New conversation store |
| Verification | Files verified on disk; launches/system/desktop trust own result | `verify() -> bool + evidence` on every tool; completed only if verified | Verifiers for apps, system, desktop, browser |
| Timeouts | Thread pool; cannot kill | Worker process killable on timeout | Process-based runner |
| Approvals | Hash-bound, single use, expiry; bare "yes" approves on-screen action | Medium = preview, voice yes OK; High = click required; 120 s expiry | Channel-aware approval (voice vs click) |
| Voice | Browser Web Speech + browser TTS | sounddevice + Silero VAD + Groq Whisper; Orpheus / edge-tts / SAPI; barge-in; WS state push | New backend voice service |
| Retries | Provider cooldown only | Max 2 automatic retries, never destructive without re-check | Retry policy in executor |
| Metrics | Load check script | Latency targets + 300-command NLU test set | Eval harness + dataset |

## Proposed phases (each on its own branch, small commits, full suite before "done")

| Phase | Goal | Main files | Acceptance |
|---|---|---|---|
| 13 | **Plan schema v2 + strict JSON-schema builder** from registry (tool enum, nullable optionals, `additionalProperties:false`); adapter v2 -> existing executor | `ai/base.py`, new `ai/plan_schema.py`, `tools/registry.py` | Schema validates against Groq strict rules; invented tool rejected; all existing tests green |
| 14 | **PlannerProvider + Groq structured-output planner** with fallback chain, 429 backoff, usage per plan, few-shot system prompt (8-12 examples, 4 languages) | `ai/planner_provider.py`, `ai/groq_provider.py`, `ai/resilient_provider.py`, `usage.py` | Scripted provider tests; same validator for all providers; live test opt-in |
| 15 | **Local fast path with confidence** (normaliser + rapidfuzz), Groq only < 0.85; NLU test set (300 commands) + eval script | `ai/speech_commands.py`, new `ai/local_matcher.py`, `tests/nlu/` | >= 90% intent+tool, >= 85% args, 0 invented tools on local+mock |
| 16 | **Conversation memory + references** ("close it", "the second one"), desktop context collector | new `memory.py`, `orchestration/local_agent.py`, `tools/desktop.py` | Follow-up tests in 4 languages |
| 17 | **Verify-everything + killable worker process + retry policy** | `tools/base.py`, `executor.py`, `tools/system_worker.py`, all tools | Every tool has `verify()`; timeout kills worker; no "completed" without evidence |
| 18 | **Approval channels** (voice may approve medium; high needs click; 120 s) | `security/approvals.py`, `main.py`, frontend | Bypass tests incl. voice-approving-high |
| 19 | **Backend voice loop** (hotkey, sounddevice, Silero VAD, Groq Whisper, TTS chain, barge-in, WebSocket states) | new `voice/`, `main.py`, frontend | Latency measured: local < 2.5 s p90 of 30 runs |
| 20 | **Window control + live pilot** of never-run tools on a real Windows PC | `tools/desktop.py`, `scripts/verify_windows.py` | Pilot checklist executed by a person |

WhatsApp and software install stay out of scope until 13-18 are done (rule 8: pre-fill only).

## Open decisions (need owner answer before the affected phase)

1. **Groq tool-calling agent loop** (`groq_provider.py` + `executor.py` agent path) works today. The brief requires one structured-output call. Proposal: add the new planner as default, keep the agent loop behind `AI_MODE=agent` for one release, then remove. (Phase 14)
2. **Approval semantics change**: today a bare "yes"/"haan" approves the one on-screen action at any risk level. The brief requires a click for high risk. This tightens the security model. (Phase 18)
3. **Windows-only verification**: this cloud container is Linux. Hardware, window, voice-device and latency work can be unit-tested here but must be verified on the Windows PC by a person.
4. **New dependencies**: rapidfuzz, sounddevice, silero-vad (torch or onnxruntime — ~large), edge-tts. Silero via onnxruntime is preferred to avoid torch.
