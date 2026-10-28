# Phase 8 Completion Report: browser integration

Date: 2026-10-27. Nothing committed. No real Chrome/Edge profile was touched and the extension was **not loaded into any browser**.

## Review (read in full)
`browser-extension/background.js`, `manifest.json`, `setup.html`, `backend/app/browser_bridge.py`, `backend/app/tools/browser.py`, `ai/browser_commands.py` tests.
Already sound: close requires the exact tab id plus `expected_url` still matching; incognito excluded; media control limited to YouTube hosts and checks the real `video.paused` state; `open` accepts only http(s) without credentials; duplicate request ids replay the cached result rather than re-running; only one connected profile is used.

## Defects found and fixed
| ID | Severity | Finding | Fix |
|---|---|---|---|
| B-18 | High | `/browser/connect-token` gave the bridge token to any local caller that set one header, and the WebSocket origin check could be forged by any local process, so a non-extension could impersonate the browser and fabricate "tab closed" results | Endpoint now needs the API bearer token. The extension obtains it by one-time **pairing**: the app's setup link carries the token in the URL fragment, a content script on that page passes it to the extension, which validates sender id and page URL, requires >= 32 chars and stores it in `chrome.storage.local`. Unpaired extensions make no network call (badge PAIR) |
| B-27 | Medium | WebSocket did not check the Host header | Non-local Host rejected |
| B-28 | Medium | Tab URLs (query strings, fragments, often session tokens or private search text) were returned to the UI and could reach an AI provider | Output URLs are reduced to scheme, host and path; the exact URL stays internal for the close guard |
| B-29 | Medium | Extension-supplied data was trusted (`t["id"]` on any shape; extra result keys passed through) | Malformed tab records dropped, titles/URLs length-bounded, and only known result fields are copied |
| - | Low | `setup.html` showed a stale developer-machine path | Replaced with a generic instruction; pairing steps added |

## Results (executed)
- Python 3.12 + SDKs: **414 passed, 1 skipped**. Python 3.14: 388 passed, 13 skipped. `tsc` + build pass.
- Node extension tests: existing controls test passes; new `test_pairing.cjs` passes (sender validation incl. foreign page/other extension/short token, unpaired makes zero requests, Bearer header sent, 401 leaves no socket, listener stores token only for an accepted sender).
- New `tests/test_phase8_bridge.py` (11). Mutation check: removing the connect-token protection and the Host check each made tests fail; code restored.
- Real browser (built-in pane, throwaway server): the app's setup link is rendered with the session's token, `/browser/connect-token` returns 401 without and 200 with the bearer token, setup page and `pair.js` are served.

## NOT VERIFIED
- **Live Chrome/Edge**: no extension was installed, so pairing, the content script, connection, tab inspect/close and YouTube pause/resume were never exercised on a real browser. Chrome MV3 behaviour (service-worker sleep, `chrome.storage` timing, content-script match on a URL with fragment) is untested. Media pause/resume against real YouTube is untested.
- The extension is hard-wired to port 8000 (manifest host permission and `API` constant).
- A process with access to the API token file (same Windows user) can still pair/impersonate; the bridge does not pin an extension id.
- `control_browser` close is LOW risk (auto-approved when the target is a unique matched tab); closing a tab with unsaved web-form content would lose it. Accepted, not changed.
- No re-pairing/revocation flow: rotating the token file requires re-pairing manually.
- Safari/Firefox are unsupported; Edge is untested.
