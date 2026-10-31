# End-to-end UI tests (Playwright)

Real backend (temp database, temp home folder, real local tools) + the built UI + Chromium.
The microphone is faked: `window.__speak(text)` delivers a transcript to the app's speech recogniser.

Run (from `frontend/`, after `npm run build`):

```
set AGENTDESK_PYTHON=..\backend\.venv\Scripts\python.exe   (Windows; defaults to that path anyway)
npm i --no-save playwright && npx playwright install chromium   (first time only)
npm run test:e2e
```

| file | what it proves |
|---|---|
| `new_user.test.mjs` | first run: onboarding -> speak -> live transcript -> action preview (medium risk, exact path, Approve focused) -> approve -> **verified** folder on disk, timed (< 3 min) |
| `flows.test.mjs` | keyboard-only flow with focus trap and inert background; high-risk card (red, Reject focused, Esc rejects, spoken "yes" refused); voice approval of medium risk; memory add/edit/delete + secret guard; settings (persona, strict policy, listen mode off); mini orb; accessible names on every control |

The fake microphone means these tests do not measure speech recognition quality; see `docs/USABILITY_TEST.md` for the human test.
