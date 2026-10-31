# NLU evaluation set

`commands.jsonl` — 300 commands (en 92, roman_ur 88, ur 60, hi 60), one JSON object per line:

| field | meaning |
|---|---|
| `id` | `<lang>-<nnn>` |
| `lang` | `en`, `roman_ur`, `ur`, `hi` |
| `split` | `dev` (201) or `holdout` (99, every third item per language) |
| `command` | what the user says |
| `context` | `null`, or `{"turns": [...]}` with the previous turn(s): command, steps, status, `results` (e.g. `candidates`) |
| `expected.intent` | one of the intent enum in `app/nlu/schema.py` |
| `expected.needs_clarification` | true only for intent `clarify` |
| `expected.steps` | `[{tool, args, depends_on?}]`; args are validated against the tool registry |

Conventions:
- Known places are `~/Desktop`, `~/Documents`, `~/Downloads`.
- A file/folder given only by name is resolved by `find_paths` first; the next step refers to it as `"$0"` with `depends_on: 0`. `open_folder` / `open_file` accept names directly.
- `"*"` as an expected argument value means "any non-empty value" (used for email subject/body the model must draft).
- Increase/decrease without a number means 10.
- `clarify`, `unsupported` and `chat` have no steps.

The set was written and committed **before** the local matcher, and the holdout split is not used for tuning.
Scored by `scripts/eval_nlu.py`.

## Changes

- **2026-10-31 (Phase 18):** 4 items (WhatsApp messages: `en-*`, `roman_ur-*`, `ur-*`, `hi-*` "…whatsapp… message…")
  relabelled from `unsupported` to `whatsapp_draft` / `whatsapp_open_chat {contact, text}`, because the product
  can now pre-fill a WhatsApp chat (the user still presses Send). No other item changed.
