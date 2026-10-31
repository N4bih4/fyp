# Pilot findings and fixes (2026-10-31)

Automated pilot (`backend/scripts/pilot_run.py`) on a second machine: Linux cloud container, not the
user's Windows PC. First run against release 0.1.0: **12 passed, 0 failed, 8 not run**. After the fixes,
against release 0.2.0: **13 passed, 0 failed, 7 not run** (`2026-10-31-pilot-linux.md`). The human pilot
on a second Windows PC (`docs/audit/PILOT_CHECKLIST.md`) has **not** been run.

| # | Finding (how it showed up) | Impact | Fix | Proof |
|---|---|---|---|---|
| 1 | Checklist B3 "write a file, overwrite it, Undo" could not be done by command: the local parser had no write/overwrite rule; without a cloud key the user got "command clear nahi hui". | A core safety path (overwrite + undo) was unreachable by voice | Older local parser first, then the Phase 15 local matcher as a fallback for confident, fully valid plans (no cloud). New "overwrite X with Y" -> `write_text_file overwrite=true` (high risk). The matcher also no longer reads "first version" as "the first one". | `test_write_and_overwrite_by_command_use_the_local_matcher`; pilot B3 PASS |
| 2 | Pilot metrics had no row for commands that were not understood (they stop at `awaiting_input`). | The pilot could not measure recognition failures — the most important number | Exported with status `not_understood` (automatic CSV and `/metrics/tasks.csv`) | `test_not_understood_commands_are_counted` |
| 3 | A Windows-only failure was categorised `other` in metrics. | Pilot analysis would mix platform gaps with real errors | New error category `unsupported_platform` | same test |

Not found by the automated pilot but already known (see STATUS): browser speech recognition needs internet;
the desktop shell and media/WhatsApp/winget tools are unverified on Windows; the planner still does not use
saved memories.
