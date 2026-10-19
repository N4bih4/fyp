# Security model

## Risk categories

| Risk | Examples | Policy |
|---|---|---|
| Low | `open_application` (configured trusted apps or uniquely matched installed Start Menu apps), `open_folder`, `list_folder`, `open_url`, `web_search`, `play_youtube_video` on explicit request, `read_text_file`, `open_file`, `list_trash`, desktop inspection, bounded desktop input or a named window close in an explicitly named app, reading system brightness/volume/Bluetooth state | Auto-approved |
| Medium | `create_folder`, `copy_file`, `compose_email`, `move_file`, `rename_file`, `compress_folder`, `extract_file`, `take_screenshot`, `restore_file`, new text document, changing brightness/volume or Bluetooth state | Needs user confirmation |
| High | `delete_file`, file replacement, `download_web_content`, `open_application` (unapproved app), unnamed/mismatched window close, desktop input targeting an unnamed/mismatched app | Needs **explicit** approval |

The AI proposes; the **backend disposes**. Risk is computed server-side from the
tool and its validated arguments — the model cannot downgrade its own risk.

## Path policy

- Only **absolute** paths are accepted for mutating file tools.
- `create_folder` may create a folder anywhere the operating system grants the
  backend process permission. It always requires user confirmation.
- Delete accepts an absolute path anywhere the OS permits, but still requires
  explicit user approval. It moves only files or empty folders into
  AgentDesk Trash; non-empty folders and filesystem roots are refused. Trash
  data stays beside the deleted item while its restore record is kept inside
  an allowed directory.
- Copy, move, rename, zip, edit, and downloads are fully resolved
  (symlinks, `..`, `.`) and must lie inside one of the
  `AGENTDESK_ALLOWED_DIRECTORIES`. Anything else is rejected — including
  traversal attempts like `..\..\Windows\System32`.
- `open_folder` and `open_file` may open an existing path the user named
  (including other drives such as `D:\`) without adding it to the write
  allow-list. They do not create, modify, or delete files.
- Allowed roots themselves can never be deleted.
- Move/rename/compress refuse to overwrite existing destinations.
- Downloads and documents are restricted to allowed directories. Downloaded
  content is limited to 20 MB; local/private network hosts and overwrites are
  blocked. Only direct file URLs and ordinary HTML pages are supported.
- Copy refuses existing destinations and symbolic links. Email compose only
  opens a local `mailto:` draft; sending is not implemented.
- Windows application launch resolves installed Start Menu shortcuts only.
  Exact names and high-confidence unique spelling matches can launch without
  approval; ambiguous or unmatched names are not auto-approved. Executable
  commands and file paths are never accepted as application names.
- Delete moves a file or empty folder to `.agentdesk_trash`; restore refuses
  to overwrite an existing path. This is separate from the operating system's
  Recycle Bin.

## Archive safety

Extraction is protected against **zip-slip**: any archive member that would
escape the destination folder aborts the operation.

## Execution safety

- No arbitrary code: the AI returns JSON `{tool, args}`; unknown tools and
  invalid arguments are rejected before anything is stored.
- Per-tool timeout (`TOOL_TIMEOUT_SECONDS`); timed-out tools report failure.
- Idempotency keys prevent duplicate task creation; finished tasks are never
  re-executed; a failed action skips the rest instead of continuing blindly.
- Errors are logged server-side; API responses contain safe messages only.
- Desktop input is limited to eight validated actions per call, checks that the
  requested window title matches exactly one open window, and enables PyAutoGUI's
  failsafe. Auto-approval applies only when both the target app and an action
  intent are present in the user's command, including named close requests.
  Unnamed or mismatched closes still require approval. Closing is successful
  only if the target disappears.
- System-setting controls accept only bounded brightness/volume percentages and
  explicit Bluetooth on/off actions. They use Windows device APIs and report
  unsupported hardware or denied access as failures; changes require confirmation.

## Secrets

- Groq/OpenAI keys belong in `backend/.env` (git-ignored). They are read
  server-side only, never sent to the frontend, never logged, never committed.
- `/config/status` reports only whether a key is configured.
- Rotate any key pasted into chat, source files, screenshots, or support
  requests. Do not reuse exposed keys.

## Known limitations (MVP)

- The backend binds to **localhost only** and has **no user authentication**.
  It is a single-user local assistant. Do not expose it to a network without
  adding authentication, TLS, and a secrets manager.
- Screenshots stay on disk inside an allowed directory; they are never sent to
  the AI provider automatically.
- When the user asks the assistant to read a text document, its contents are
  returned to the model and therefore sent to the configured AI provider.
  Reading is limited to 50,000 characters per file.
- Voice recognition uses the browser Web Speech service, not a local/offline
  recognizer. The browser's speech service may process audio over the network;
  the recognized transcript is sent to the configured AI provider. Hands-free
  retries network failures while enabled but cannot transcribe during an outage.
  Spoken commands received while another task is running are queued and run
  sequentially; approval-gated actions still require approval in the UI.
- Desktop control is best-effort and foreground-only. Screen coordinates,
  protected windows, save prompts, and app-specific behavior can prevent
  actions. Screen-image understanding is not provided.
- YouTube search/play opens a matching public watch page when it can identify
  a close title match. Autoplay can still be blocked by the browser or YouTube,
  so opening a video does not guarantee playback. YouTube/video downloading is
  unsupported.
