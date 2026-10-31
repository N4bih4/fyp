# Integrations (Phase 18)

| Tool | Risk | What it does | Verified by | Never does |
|---|---|---|---|---|
| `media_control` | low | Media keys: play, pause, play_pause, next, previous, stop (Spotify, YouTube, any player) | Windows media session (SMTC): playing/paused status, or a new track title for next/previous | toggle a player already in the asked state |
| `play_youtube_video` (updated) | low | Opens the best match; asks the browser extension to press Play if autoplay is blocked | Windows media session reports **playing** (search-results pages: the YouTube window) | claim playback that did not start |
| `whatsapp_open_chat` | medium | Opens WhatsApp Desktop on a chat with the message typed in (`whatsapp://send`) | WhatsApp window open; when UI Automation can read the box, it must contain the draft | press Send or any key in WhatsApp |
| `winget_install` | **high** | Installs one exact WinGet package ID after explicit approval (accepts its license) | fresh `winget list --id <ID> --exact` shows it | install a guessed name; get killed mid-install |
| `compose_email` (unchanged) | medium | `mailto:` draft | draft window | send (no SMTP code exists; test enforces it) |

WhatsApp contacts: only numbers you saved on the Memory page ("Ahmed: +923001234567"). Local numbers
without a country code (0300...) are refused rather than guessed.

Voice: a spoken "yes" can approve `whatsapp_open_chat` (medium) but never `winget_install` (high: click Approve).

## Record one live run of each tool (Windows PC)

From `AgentDesk_AI/backend` with the venv active. Each command writes `docs/live_runs/<time>-live_check-windows.json`.

```
python scripts/live_check.py --only media_control --media --record
python scripts/live_check.py --only play_youtube_video --gui --record
python scripts/live_check.py --only whatsapp_open_chat --whatsapp-phone +<your own number> --record
python scripts/live_check.py --only winget_install --install-id <small package you want, e.g. JernejSimoncic.Wget> --record
```

Have music playing (Spotify or a YouTube tab) before the media run; it toggles play/pause twice so it ends as
it started. The WhatsApp run only opens the chat with "AgentDesk live check - not sent"; close it without sending.

Browser extension: `cd frontend && npm run test:browser` (real Chromium + real extension; see BROWSER_CONTROLS.md).
