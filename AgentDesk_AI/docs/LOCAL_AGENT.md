# Agent X local agent

## Execution pipeline

Text or browser speech transcript -> speech normalization -> local intent rules -> local file/window discovery -> clarification/preview when ambiguous -> tool schema validation -> permission/confirmation -> tool execution -> verification -> result and saved task state.

This is a deterministic local agent, not a newly trained language model. It has real tools, workflow state, bounded multi-step plans and confirmation handling. PC commands no longer require Groq. Cloud reasoning is separately available for free-form tasks.

## Commands

- Volume: volume up/down, valume kam kar do, volume volume down, decrease volume by 20 percent, set volume to 35%, mute/unmute, volume band kar do.
- Brightness: brightness up/down, bright ness increase, meri brightness zyada karo, set brightness to 45%.
- Bluetooth: bluetooth on/off, blue tooth on kar do. Bluetooth changes retain approval because they can disconnect devices.
- Theme: dark mode kar do / light mode. The tool changes both Windows app and system theme for the current user and reads back the actual values. Apps with their own theme settings may not follow Windows. The web UI follows browser/OS dark-mode preference.
- Hindi and Urdu equivalents of these settings are normalized. Only high-confidence setting-name spelling variants are fuzzy matched. Unknown/contradictory commands ask for clarification instead of choosing a destructive operation.
- Open known apps: open Notepad, open VS Code, WhatsApp kholo. V S Code pauses are normalized. Code X is ambiguous and prompts for clarification.
- Close: close Notepad, close window followed by the exact title. Local window inspection requires a unique title match.
- Multi-step: volume down aur brightness up. Up to four supported simple commands may be joined with and/aur. All parts must be understood before execution starts.
- Follow-up: after a setting succeeds, aur kam karo applies to the last successful setting.
- Files: create folder Study in Documents; copy folder <source> to <destination>; move file <source> to <destination>; rename folder <source> to <name>; delete folder <name/path>; open folder <name/path>; list folder <path>.
- Missing create location: create folder Study -> asks where -> reply Documents or an exact parent path.
- Ambiguous folders: delete folder lecture -> numbered candidates -> preview 1 -> opens it -> haan -> exact deletion proposal -> approval popup. No mutation occurs merely from previewing.
- Non-empty deletion: delete folder <path> including contents. The flag and path are shown in approval; contents move to restorable internal Trash.
- Local search: search <query> opens browser search results, without an LLM call.
- Downloads: download VS Code searches packages locally using WinGet. Then download package <exact ID> from winget/msstore requests approval for download. Package discovery/download requires internet, but no Groq requests.
- Email: compose email to user@example.com with subject Update and body Hello opens a draft after approval. Generating prose from an open-ended topic needs explicit cloud reasoning.
- Other tools: take screenshot, compress folder <absolute path>, extract archive <absolute path>, read file <absolute path>, open website example.com.

## Cloud policy

AI_CLOUD_MODE=explicit is the default. Unknown PC commands ask for clarification. Prefix AI:, research or explain for requests needing cloud reasoning. Set AI_CLOUD_MODE=automatic only if you want unmatched commands to use cloud AI automatically. Groq and optional backups retain their existing limits, keys and quota handling.

## Boundaries

This agent recognizes supported patterns and aliases; it cannot understand every accent or arbitrary sentence offline. Speech-to-text is still the browser's online speech recognition service; typed local commands do not need that service. Browser settings, installed applications, drivers and OS permissions affect actual operations. Search and downloads need internet. File paths still obey tool permissions; no blanket access restrictions were removed.

The speech pause window is now 2.2 seconds, allowing slightly longer pauses before submitting a transcript. Misheard ambiguous targets are clarified instead of silently mapped to file/app operations.

Verification: 169 backend tests passed, one optional live-provider test skipped, and production frontend build passed. Tests cover multilingual/spelling variants, conflict rejection, local multi-step/follow-up commands, file discovery/preview/approval, destination clarification and theme tool responses. These tests mock OS side effects; live microphone and individual hardware behavior still require testing on the PC.


## Real voice transcript regression fix

Added grammar translation for Urdu, Hindi and Roman Urdu folder/file/app open commands while keeping target names separate. The actual failed transcript for the semester folder now creates a local discovery workflow rather than a generic cloud-reasoning message. Limited bilingual lookup aliases (for example semester/sixth) suggest real existing paths and require selection when names differ. They never synthesize filesystem paths or silently choose destructive targets.

Added the actual volume-up, PC Bluetooth-off, brightness-decrease and volume-percent transcript spellings from task history. Clarification-only local tasks now have awaiting_input status instead of completed; voice input remains ready for the user's answer. Regression suite: 183 passed, one optional live-provider test skipped; frontend production build passed. These tests do not establish perfect accent recognition: microphone transcription errors can still require clarification.

## Runtime and browser additions

The launcher now prefers backend/.venv, which contains the Windows hardware dependencies. Hardware controls run in bounded worker processes to prevent COM thread faults or native library failures from bringing down the API. Repeated live volume reads, brightness reads and Bluetooth reads succeeded after this change. The user-provided D:\6th sem folder was found and opened through the local workflow.

For exact browser tabs and YouTube state controls, see [Browser controls setup](BROWSER_CONTROLS.md). This requires the user-installed Chrome/Edge bridge.
