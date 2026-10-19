# API reference

Base URL: `http://127.0.0.1:8000`. Interactive docs: `/docs`.

## Health & config

### `GET /health`
```json
{"status": "ok", "version": "0.1.0"}
```

### `GET /config/status`
Never exposes the API key — only whether one is configured.
```json
{
  "ai_provider": "mock",
  "ai_model": "openai/gpt-oss-120b",
  "ai_configured": true,
  "mock_mode": true,

  "allowed_directories": ["C:\\Users\\you\\Documents\\AgentDeskTest"],
  "approved_applications": ["chrome", "notepad", "calc", "explorer"],
  "platform": "Windows"
}
```

### `GET /tools`
Lists the registered tools with descriptions, risk levels, and JSON schemas.
`control_desktop` can inspect the foreground window or execute up to eight
bounded mouse/keyboard steps, including closing a uniquely matched window.
Inspection is low risk. Input actions are auto-approved only when the user's
command names the target app and describes the action; unmatched or unnamed
targets still require approval. Named close requests are auto-approved the same
way; unnamed closes still need approval. A close is verified by checking that
the target window is gone.

The registry also includes `web_search` (opens Google results in the default
browser), `read_text_file`, `write_text_file`, `open_file`, `list_trash`,
`restore_file`, `download_web_content`, `copy_file`, and `compose_email`.
Most file operations are restricted to
configured allowed directories. `create_folder` and `delete_file` are
exceptions: after user
confirmation, it may create a folder at any absolute path the operating system
permits; `delete_file` needs explicit approval and moves only files or empty
folders to AgentDesk Trash so they can be restored. Replacing a document, restoring from the
AgentDesk Trash, and downloading content require approval. Downloads are
limited to 20 MB; local/private network hosts, overwrites, and video extraction
are blocked. Set `save_as_webpage: true` to save a public HTML page; otherwise
HTML responses are not treated as file downloads.

Deleting a file or empty folder moves it to AgentDesk's internal Trash rather
than permanently removing it. `list_trash` returns `trash_id` values, which
`restore_file` accepts. This Trash is not the Windows Recycle Bin.

### Text documents

`write_text_file` creates a UTF-8 text document inside an allowed directory.
It will not overwrite an existing file unless `overwrite: true` is explicitly
set; replacements require high-risk approval. `read_text_file` returns at most
50,000 characters. `open_file` opens an existing file using its default desktop
application.

### Copy and email drafts

`copy_file` copies a file or directory inside allowed directories; it will not
overwrite existing destinations and refuses symbolic links.

`compose_email` prepares a draft in the system's configur ed email application
using a `mailto:` link. It never sends email; the user reviews the recipient,
subject, and body, then manually sends or rejects the draft in that application.
The email application must be configured in the operating system.

```json
{"to": "user@example.com", "subject": "Project update", "body": "Hello..."}
```

### Web search and downloads

`web_search` opens Google results, or YouTube's own search results when
`site` is `youtube.com`. On Windows, YouTube search/navigation reuses an
already-open YouTube window when possible; otherwise it opens through the
default browser. It navigates the current YouTube tab and does not select or
start a video automatically.

For an explicit request to play a named video/song, `play_youtube_video`
searches YouTube for a close title match and opens its watch page with autoplay
requested, reusing an existing YouTube window when available. If the title
match is unclear or YouTube search cannot be parsed, it opens the search results
instead. YouTube and browser autoplay settings can prevent playback; the tool
reports a selected video as opened, not playback-confirmed.

```json
{"query": "Hindi cartoon song title"}
```
```json
{"query": "relaxing piano music", "site": "youtube.com"}
```

`download_web_content` downloads a direct public file URL or saves an HTML
page, only inside an allowed directory:
```json
{"url": "https://example.com/report.pdf", "output_path": "C:\\Users\\you\\Documents\\report.pdf"}
```
For HTML pages set `save_as_webpage` to `true`. The response is capped at 20 MB
and existing destination files are never overwritten.

## Tasks

### `POST /tasks` — plan a command
```json
// request
{"command": "Create a folder called FYP in Documents", "idempotency_key": "optional-unique-key"}
// response: TaskOut (status: awaiting_approval | approved | completed | failed)
```
If `idempotency_key` matches an existing task, that task is returned unchanged —
no duplicate planning or execution.

### `GET /tasks?limit=20` — history (newest first)
### `GET /tasks/{id}` — one task with its actions

### `POST /tasks/{id}/approve` — approve pending actions
```json
{"action_ids": ["<id>", "..."]}   // or {} to approve all pending
```

### `POST /tasks/{id}/reject` — reject (nothing runs)

### `POST /tasks/{id}/run` — execute approved actions
Runs approved actions in order with per-tool timeouts and verification.
Returns the finished task. Safe to call twice: finished tasks are never
re-executed. Returns `409` if actions are still awaiting approval.

### `POST /tasks/{id}/cancel` — cancel a pending task

## TaskOut shape

```json
{
  "id": "...", "command": "...", "status": "completed",
  "plan_note": "[mock AI]",
  "error": null,
  "created_at": "...", "updated_at": "...",
  "actions": [
    {
      "id": "...", "seq": 0, "tool_name": "create_folder",
      "args": {"path": "C:\\...\\FYP"},
      "risk": "medium", "status": "succeeded",
      "result": {"success": true, "output": {"path": "..."}},
      "verification": {"passed": true, "checks": ["folder exists: True"]},
      "error": null
    }
  ]
}
```

Task statuses: `created`, `awaiting_approval`, `approved`, `executing`,
`completed`, `failed`, `cancelled`, `rejected`.
Action statuses: `pending`, `approved`, `rejected`, `running`, `succeeded`,
`failed`, `skipped`, `cancelled`.
