# AgentDesk AI — STATUS

Single source of truth for "what is done". Updated at the end of every session.
Older evidence: `FEATURE_AUDIT.md`, `audit/FEATURE_TRACEABILITY_MATRIX.md`,
`audit/FINAL_ACCEPTANCE_AND_SECURITY_REPORT.md`, `audit/phases/PHASE_*_COMPLETION.md`.

## Session log

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
