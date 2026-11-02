# Final measured report: "control every app by voice" upgrade (U1–U8)

Everything below was run on the developer PC (Windows 11) unless it says otherwise. Numbers come from the files named in each row. Where something was
**not** run, it says so. Sources: `docs/STATUS.md` (sessions 22–29), `docs/eval/*`.

## Per milestone

| Milestone | What it adds | Measured | Not measured / open |
|---|---|---|---|
| U1 understanding | App/file/folder index, sound-alike matching (English, Roman Urdu, Hindi), Whisper vocabulary hint, correction memory ("no, I said Firefox") | 218 text cases: dev 153 → 100% target ok, 0 wrong actions; holdout 65 → 98.5% ok, 84.7% resolved without asking, 1 wrong action, 0 wrong high-risk (`docs/eval/u1_eval.json`). Real index: 1,764 names in 2.7 s, lookup median 3.6 ms | Real accented / Urdu speech not measured (text only); Whisper hint effect not A/B tested |
| U2 speed | Latency log with budgets, early acknowledgement, 20b/120b routing, warm Groq connection | 30 runs: Whisper p50 1112 ms; plan p50 11 ms; execute+verify p50 20 ms; done within 5 s 30/30. Fast path 99.2% of 250 gold commands, 0.16 ms (`docs/eval/u2_latency.json`) | **Acknowledgement budget MISSED**: estimated p50 1711 ms vs 1.5 s (Whisper alone 1.1 s here). Launching apps, mic/browser/playback stages not measured |
| U3 conversation | Task session, stop/wait/repeat/undo phrases, "Anything else?", bounded re-check | 48 tests incl. 10 scripted multi-turn conversations; text check on the running backend | No spoken conversation; barge-in 300 ms not measured |
| U4 UI Automation (layer 2) | `ui_inspect`, `ui_act` on any app | Live on real Calculator, Notepad, Explorer, Settings, Chrome: **32/33 (97.0%)** (`docs/eval/u4_live.json`); first run was 0/31 before two fixes | Word and Excel not installed here; 33 of the 50 target live actions; planner choosing the tools not run on Groq |
| U5 terminal + browser | Policy-gated terminal with live window; YouTube/browser controls (extension 1.2.0) | Terminal live 9/9 as expected, 0.07–0.2 s per safe command, a 60 s sleep killed after 5 s (`docs/eval/u5_terminal_live.json`); 732 + 86 tests | Real youtube.com in real Chrome with the extension: **not run** (extension not paired here) |
| U6 e-mail + messages | OAuth (PKCE), dictation, voice edits, read-back, hash-bound "yes, send it", Sent-folder check, chat sending | 79 tests on a fake mailbox, mock HTTP and a fake chat window incl. every send-rule bypass | **No real mailbox or real WhatsApp/Telegram/Teams was touched** (no OAuth client id / test mailbox); no spoken run |
| U7 vision (layer 3) | `screen_act`: screenshot, OCR + UIA boxes, numbered picture, model picks a box id, verify by re-screenshot | 20 steps on a UIA-blind app with ground truth: run 1 20/20, run 2 18/20, **run 3 20/20** (18 also verified by the tool), median 5.2 s, max 22.9 s (rate-limit wait) (`docs/eval/u7_live*.json`) | Verifier thresholds were tuned on the same 20 tasks; "a few seconds" not consistently met on free Groq tier; one app, one monitor |
| U8 polish | Settings for new features (`screen_vision`, `terminal_window`), user guide, demo script, clean-install check, this report | See "U8 checks" below | Install on a **second physical PC** not done (no second PC) |

## U8 checks
- Full backend suite: see `docs/eval/u8_pytest.txt` (the result line is quoted in the final reply of this milestone).
- Clean install: the committed code (`git archive HEAD`) was extracted into an empty folder, a new virtual environment was created, `requirements.txt` + `requirements-dev.txt` installed, and the app imported (`app.main`, `app.tools.screen`, `app.vision.ocr`). Result is in the milestone reply. This is a clean *folder and environment* on the same PC, not a second PC.

## Safety properties (enforced in code, covered by tests)
- Layers in order: native tool → UI Automation → vision; each action logs which layer ran.
- The model never supplies coordinates: it names a box number from the detected list; unknown numbers are refused.
- Risk is decided by the server from the arguments. High risk (delete/pay/send/install, shells) needs a click on Approve; a spoken yes is refused.
- E-mail and chat: nothing is sent without read-back and a spoken "yes, send it" tied to the exact text (hash); edits void it.
- Passwords, PINs and one-time codes are never read aloud, stored or typed; password-looking boxes and fields are refused.
- Text from screens, pages, e-mails and files is treated as data in every prompt.
- Payments are never completed. "stop" ends the running task.

## What would still need a person
1. Run `scripts\check_u1.ps1` … `check_u7.ps1` and the by-hand lists in them (spoken checks, real mailbox with an OAuth client id, real WhatsApp, real YouTube with the extension).
2. Install on a second PC from the release zip and run `scripts\check_u7.ps1 -NoLive` there.
3. Confirm Render deployed the latest backend commit.
