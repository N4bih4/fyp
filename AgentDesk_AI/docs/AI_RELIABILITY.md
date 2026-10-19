# API limits and optional backups

Groq remains the primary provider. No keys or subscriptions were changed.

## Improvements

- Exact supported brightness/volume and known-app open commands are parsed locally and use zero language-model requests, even if the API key is missing or cloud quota is exhausted. Mixed, ambiguous and destructive instructions are not guessed by this parser.
- Simple English, Roman Urdu, Hindi and Urdu variants are supported; unfamiliar phrasing goes to AI.
- The system prompt is shorter and common English requests get only relevant tool definitions. Other requests retain the full catalogue. Recent tool observations are bounded.
- SDK-level hidden retries are disabled; the existing bounded retry policy remains in control.
- A shared in-process cooldown prevents successive tasks from immediately hammering the same rate-limited key/model. It resets on backend restart; the persisted task retry time survives restarts.
- A 429 pauses a task as waiting_retry with a provider reset time, rather than losing completed work. Press Resume task after that time. Repeated early presses send no extra model request. Completed tool actions are not replayed. Task history lets you reopen a paused task after issuing another command.
- An explicitly configured secondary provider can continue the same model conversation after a primary 429. It still goes through the same validated tools and confirmation flow. UI shows when the backup was used. Authentication/configuration errors do not silently become fake/offline AI success.

## Optional backup setup

Put secrets only in backend/.env; do not paste them in chat or frontend code. Restart the backend after changing configuration.

Gemini option:
```dotenv
AI_PROVIDER=groq
AI_FALLBACK_PROVIDER=gemini
AI_FALLBACK_MODEL=gemini-3.8-flash
GEMINI_API_KEY=your_real_key_here
```

OpenAI option:
```dotenv
AI_PROVIDER=groq
AI_FALLBACK_PROVIDER=openai
AI_FALLBACK_MODEL=gpt-5.4-mini
OPENAI_API_KEY=your_real_key_here
```

Leave AI_FALLBACK_PROVIDER=none to disable cross-provider fallback. Optional providers have their own limits, data policies and potential billing. Configured means a key is present, not that credentials/billing were successfully verified. During this change, the existing OpenAI key failed a read-only verification with HTTP 401, and no Gemini key was configured. Consequently no backup was enabled. Provider adapters and switching were verified using mocked SDK responses; live backup generations were not tested.

For frequent production use, a funded plan with adequate limits plus local handling and an independently configured backup is more dependable than repeatedly moving between free quotas. A different free API is not unlimited and cannot guarantee higher availability for this account. Nothing in the code bypasses provider quotas.

Official references checked October 19, 2026:
- Groq limits: https://console.groq.com/docs/rate-limits
- Gemini models: https://ai.google.dev/gemini-api/docs/models
- Gemini limits: https://ai.google.dev/gemini-api/docs/rate-limits
- Gemini OpenAI-compatible tools: https://ai.google.dev/gemini-api/docs/openai
- OpenAI GPT-5.4 mini tool support/pricing: https://developers.openai.com/api/docs/models/gpt-5.4-mini
