# Phase 4 Completion Report: Windows tools

Date: 2026-10-26. Nothing committed. Only disposable data (pytest temp folders) was used. No Wi-Fi, Bluetooth, volume, brightness or other live device change was run, and no real window was typed into.

## Reviewed (line-by-line)
`tools/desktop.py` (all), `tools/packages.py` (all), `tools/web.py` (Phase 0), and in `tools/filesystem.py`: move, rename, compress, extract, write, open_file and the path helpers; `system.py` subprocess/worker section; `apps.py` open_url validation and YouTube window reuse.
**Not line-reviewed:** `filesystem.py` delete/trash/restore/find/edit internals (existing tests pass, unexamined), `apps.py` Start Menu matching and launch code, `system.py`/`system_worker.py` hardware logic, `settings_pages.py`, `browser.py`.

## Defects found and fixed
| ID | Severity | Finding | Fix |
|---|---|---|---|
| B-07 | High | Typed or key input into a named shell/console/admin window was auto-approved whenever the user's command named the app. | `is_shell_target`: such input is never auto-approved and is **refused at execution even if approved** (process name or title check). Closing, minimising and inspecting those windows still work. |
| B-20 | High (new) | `open_file` is LOW risk, opens any existing file and hands it to the OS. `.bat/.ps1/.exe/.lnk/.vbs/.js/.py/...` would run. Combined with `write_text_file`, the LLM could author then run a script. | `open_file` refuses executable/script extensions; `write_text_file` refuses to create them (`security/paths.EXECUTABLE_EXTENSIONS`). |
| B-21 | Medium (new) | `extract_file` silently overwrote existing files and had no entry/size limit. Default destination was the original folder. | Refuses if any target file exists (nothing written); limits 5000 entries / 1 GiB declared size; default destination is now `<archive>_extracted`. |
| B-22 | Medium (new) | `move_file`/`rename_file` could move or rename an allowed root (including the home folder); rename accepted `:` (NTFS alternate data stream names). | Both refuse allowed roots; rename rejects `:`. |
| B-23 | Low (new) | YouTube window reuse typed a URL into any window whose title contained "youtube", including a shell. | Shell/console windows excluded. |

Behaviour change to note: extraction without a destination now goes to `<name>_extracted`, so the existing `test_compress_and_extract` expectation still passes without overwriting.

## Results (executed)
- Python 3.12 + SDKs: **367 passed, 1 skipped** (opt-in live Groq test), 0 failed.
- Python 3.14: 341 passed, 13 skipped (no SDKs), 0 failed.
- New: `tests/test_phase4_tools.py` (31 cases): shell classification, risk policy, execute-time refusal using a fake `pyautogui`, executable-type refusal, script authoring, root move/rename, ADS names, extract overwrite/zip-slip/limit/happy path.

## Verified safe on read (no change)
`application_package`: list-form `subprocess` with `shell=False`, query regex cannot start with `-` or contain shell metacharacters, destination checked against allowed directories, timeouts reported honestly. System setting worker runs in a killed-on-timeout subprocess.

## NOT VERIFIED / open
- All hardware tools (volume, brightness, Bluetooth, Wi-Fi, Settings pages) were not exercised; `pyautogui`/`pycaw`/`screen-brightness-control`/`winsdk` are not installed in the test venv. Prior-docs claims of live PC checks remain unconfirmed by me.
- `control_desktop` was tested only with a fake `pyautogui`; real window activation, close and Alt+F4 behaviour was not run.
- Executable-extension list is a deny-list; other dangerous handler types may exist (e.g. `.docm` macros open in Word). Not addressed.
- `open_file` may still open any existing file anywhere on disk (documented design); `edit_text_file`/delete internals unreviewed.
- Roughly 50 other tools' positive/negative live behaviour is covered only by existing mock-based tests.
