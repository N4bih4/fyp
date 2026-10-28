# Phase 7 Completion Report: frontend command, approval, progress and history workflows

Date: 2026-10-27. Nothing committed. UI driven in the built-in browser against a throwaway server (port 8765, mock AI provider, temp database, temp token file, disposable files in a temp folder); the server was stopped afterwards.

## Defects found by driving the real UI
| Finding | Cause | Fix |
|---|---|---|
| Every POST from the UI returned 403 "Cross-origin request rejected" when the app was not on port 8000 | Phase 1 Origin guard allowed only fixed ports | Same-origin (Origin equals the request's own Host) is now allowed; test added (`test_same_origin_ui_on_any_port_is_allowed`). Default port 8000 behaviour unchanged |
| Command box collapsed to ~50 px wide next to the voice buttons at 1024 px | Flex row layout | Input is full width; controls wrap below |
| No progress or Pause while a run was in flight | UI polled only when the local task state was transitional, but the blocking run call kept it at "approved" | Polling also runs while any request is in flight; "Pause after current action" button shows for `executing` |

## Added UI
Pause button and Paused/Resume banner; per-action Undo status (available / unsupported / undone and verified / undo failed + reason); "Undo changes" button (with confirmation) on finished tasks; partial-completion banner; "Approve all except high-risk" label when a high-risk action is pending; "Yes, do it" now sends the displayed action ids. API client gained `pause` and `rollback`.

## Verified in the real browser (executed)
- Token handoff: opened `/#token=...`, token stored in `sessionStorage`, fragment removed from the address bar, authenticated requests succeed.
- Command -> plan: "Create a folder called ui_demo in Documents" produced an awaiting-approval task showing the exact action and path in a confirmation dialog; folder did not exist until approved.
- Approve ("Yes, do it") -> execute: task `completed`, verification "folder exists", folder present on disk.
- Undo changes: confirmation text shown, UI reported "undone and verified (removed 1 folder)", folder gone from disk.
- High-risk delete of a disposable file: dialog showed "delete file" and the path; after "Yes, do it" file removed; Undo restored it ("restored from Trash"), content verified on disk.
- Task history lists tasks and statuses. No horizontal overflow at 375 px width; layout usable.
- Backend suite after changes: 403 passed, 1 skipped (Python 3.12). `tsc` and `vite build` pass.

## NOT VERIFIED
- Pause/Resume and the partial-completion banner were not driven in the browser (the mock provider only produces single-action tasks, and the three-action pause path is covered by an API test only). The UI code for them compiles but is unobserved.
- The native `window.confirm` for Undo was stubbed in the page to avoid blocking automation; the message text was captured, the native dialog was not exercised.
- Not tested: voice input, hands-free mode, Settings panel, history click-through, reject/cancel flows, the Groq provider path, a failed task display, keyboard-only navigation, screen readers, focus trapping in the dialog.
- No automated UI tests exist; the checks above were manual and are not repeatable by CI.
- Console showed a 403 (before the origin fix, in the earlier session) and a connection-refused (after I stopped the server); no other errors seen. `/favicon.ico` returns 404 (cosmetic).
- Screenshots in this pane were scaled and unreliable for click coordinates; interaction used element references and page state, so visual polish was not judged.
