# Device control (F5)

Tools: `device_control` (`app/tools/device.py`) and `explorer_view` (`app/tools/explorer_view.py`); spoken forms in `app/ai/device_commands.py`.
Files and folders (create, rename, move, copy, delete with undo, open, find) are the older file tools; they ask first and verify on disk.

| Say | Does | Risk | Checked by |
|---|---|---|---|
| "lock my pc" | `LockWorkStation` | medium | the desktop becomes the protected (lock) one |
| "put the laptop to sleep" | sleep (not hibernate) | medium | **cannot be observed** afterwards: reported as "Windows accepted the request" |
| "restart / shut down the pc" | Windows' own timer, **10 s**, "Say cancel to stop it" | **high: click Approve** | the schedule was accepted (exit code); a spoken "cancel" / "stop" runs `shutdown /a` first |
| "keep the pc awake for 2 hours" | `SetThreadExecutionState` held by a server thread | low | the holder is alive; "stop keeping it awake" releases it |
| "how much battery is left" | OS battery reading | low | read again |
| "airplane mode on / off" | every radio off; **off restores exactly what was on** | medium | radios read again |
| "do not disturb on / off" | Windows' notification master switch | low | value read again |
| "night light on / off" | the Night light page's own button in Settings (no supported API) | low | the button name is read again; **needs the English Windows Settings** |
| "sort by date newest first", "show as details", "show hidden files", "properties of C:\...", "search this folder for X" | the front File Explorer window through the Shell object | low (hidden files: medium) | sort / view read back from the folder view; hidden from the registry; the Properties / Search Results window must appear |

## Unlock is impossible, on purpose
Windows runs the lock screen on a protected desktop; no program may type into it or drive it. There is **no unlock action**. "Unlock my pc" gets an honest answer. What the assistant can do:
keep the PC awake (so it does not sleep), and say **"welcome back"** once when you unlock after the PC was locked for 20 s or more (Settings > "Say welcome back"; a server thread watches for lock -> unlock).

## Checked on a real PC
`backend/scripts/device_live.py` (never locks, sleeps, restarts or shuts down; never touches the radios): 22/22 steps on the developer PC, each change undone (`docs/eval/f5_live.json`).
Not done live (by design): lock, sleep, the real 10-second restart / shutdown, airplane mode on. These are covered by fakes in `tests/test_f5_device.py`.
