# Browser tabs and YouTube playback

## Enable the browser bridge once

Open http://127.0.0.1:8000/browser-extension/setup.html or Settings -> Browser tab controls -> Chrome / Edge setup.

1. In the intended Chrome profile open chrome://extensions (Edge: edge://extensions).
2. Enable Developer mode and choose Load unpacked.
3. Select AgentDesk_AI/browser-extension from this project.
4. With the backend running, click the extension icon. Its badge becomes ON. The app Settings page then shows Browser connected.

The setup page displays this workspace's full folder path. Enable the bridge in one browser profile at a time; multiple connected profiles are reported as ambiguous rather than silently choosing one. This extension works in Chrome/Edge, including background tabs in that profile. It is not installed automatically and cannot be loaded into the Codex in-app browser.

## Commands (no Groq requests)

- video pause kar do / video rok do / pause video
- video chala do / resume video
- Google Drive ka tab band kar do
- YouTube ka tab band kar do
- close Gmail tab / close WhatsApp tab / close OpenAI tab
- list tabs
- close tab 123 / pause tab 123 / resume tab 123
- play Python tutorial on youtube
- youtube par Python tutorial chala do

Urdu/Hindi variants of the media and tab-close commands are recognized by the local parser. Named-video requests use the existing local web lookup and may show YouTube search results when no confident match is found. Browser autoplay policy can require a manual Play click; opening a page is not reported as verified playback.

## Matching and verification

The extension supplies actual tab IDs, titles and URLs. Known sites match real hostnames: Drive is drive.google.com, Gmail is mail.google.com, WhatsApp is web.whatsapp.com. Lookalike domains and unrelated active tabs are not substituted.

If several tabs match a close request, the task asks for a title or ID. Media commands may select a unique audible YouTube tab; otherwise multiple matches also need a choice. Pause and resume call video.pause()/video.play() and inspect video.paused, so a repeated pause does not accidentally resume. Closing verifies the exact tab disappeared. A navigation between inspection and execution aborts the action using the expected URL guard.

The bridge authenticates extension-origin WebSockets with a per-server random token. No cloud service or browser history upload is involved. The extension reads tab metadata, can close the requested tab, and has scripting permissions only for YouTube. Incognito tabs are excluded. Browser responses are time-bounded; timed-out operations are not automatically repeated.

## Verification and remaining manual step

Backend tests cover local command parsing, exact URL/ID selection, lookalike domains, duplicate tab ambiguity, missing extension behavior, and authenticated WebSocket request/result round trips. Node tests mock the Chrome APIs to check idempotent media actions, stale-navigation guards and exact tab close. Actual user's browser tabs have not been controlled because the extension still needs the user's one-time Load unpacked action.

Official APIs used:
- https://developer.chrome.com/docs/extensions/reference/api/tabs
- https://developer.chrome.com/docs/extensions/reference/api/scripting
- https://developer.chrome.com/docs/extensions/how-to/web-platform/websockets
