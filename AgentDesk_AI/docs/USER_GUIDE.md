# Agent X (AgentDesk AI) — user guide, version 0.2.0

Agent X does things on your Windows PC when you ask in English, Urdu, Roman Urdu or Hindi. Anything that
changes your files or settings is shown to you first and runs only after you approve it. When it says
**done**, it has checked the result on your PC.

## 1. Install (about 10 minutes, once)

1. Download `AgentDesk-AI-0.2.0-win.zip` and its `.sha256` file. Optional: check the checksum
   (`certutil -hashfile AgentDesk-AI-0.2.0-win.zip SHA256` must match the file).
2. Extract it, for example to `C:\Users\<you>\AgentDesk-AI`.
3. Double-click **INSTALL.cmd** (needs Python 3.12). Wait for "Installed".
4. Start it:
   - **START_AGENT_X.cmd** — opens Agent X in your browser, or
   - **START_AGENT_X_DESKTOP.cmd** — desktop app with a small always-on-top orb and a tray icon
     (one extra step the first time: it shows the `pip install` command to run).

To remove it: delete the folder and `%LOCALAPPDATA%\AgentDesk`.

## 2. First start

A three-step welcome appears: pick the language you will speak, allow the microphone when the browser asks,
and try the suggested command ("Create a folder called Demo in Documents"). A card shows exactly what will
happen; press **Approve**. The orb shows "Checking the result", then the task says **completed**.

## 3. Talking to it

- Press the **orb**, the **🎙 Speak** button, or **Ctrl+Space**, then say one command. (Settings → Listen mode:
  *Push to talk* = one command per press; *Hands-free* = always listening; *Off* = typing only.)
- Or type in the command box (press **/** to jump there) and press Enter.
- The live transcript shows what was heard; Agent X answers on screen and out loud (can be turned off).

Examples:

| What you want | Say |
|---|---|
| Volume / brightness | "volume 40 kar do", "awaz kam karo", "brightness barhao" |
| Dark mode | "dark mode laga do" |
| Apps | "notepad kholo", "chrome band kar do", "minimize word", "switch to excel" |
| Websites | "youtube kholo", "gmail chrome mein kholo" |
| Music | "next song", "agla gaana", "gaana rok do", "youtube par coke studio chalao" |
| Folders and files | "downloads folder kholo", "documents mein Lab naam ka folder banao", "temp folder delete kar do" |
| Text files | "write buy milk to C:\Users\me\Desktop\todo.txt", "overwrite <file> with <new text>" |
| WhatsApp (you press Send) | "ahmed ko whatsapp pe message bhejo ke main late hoon" |
| Email draft (you press Send) | "email ali@example.com with subject Meeting and body See you at 5" |
| Install an app | "install vlc" (shows search results) then "install package VideoLAN.VLC" |
| Follow-ups | "close it", "doosra wala kholo", "thora aur" |

## 4. Approving

The card shows each action, its risk colour and the exact files, apps or messages it touches.

- **Green / low** (open, read): runs straight away (Settings → Approval policy → *Strict* makes these wait too).
- **Amber / medium** (create, move, rename, settings, WhatsApp draft): press **Approve**, or say "haan / yes".
- **Red / high** (delete, overwrite, downloads, installs, typing into apps): you must **press Approve**.
  Saying "yes" is not enough; Enter is on **Reject** for these, and **Esc** always rejects.

Changes to files can usually be undone: open the task and press **Undo changes**.

## 5. Memory, persona and settings

- **Memory** (Alt+2): things Agent X should remember, e.g. "Ahmed: +923001234567" (used for WhatsApp) or
  "6th sem means D:\6th sem". Edit or delete any item; **Forget conversation** clears what "it"/"that" refers to.
  Passwords, PINs and keys are refused.
- **Settings** (Alt+3): name, language, reply style and orb colour; listen mode; provider (*Auto* or
  *Local only* — nothing is sent to a cloud AI); approval policy; usage; start with Windows (desktop app).

## 6. Browser tabs (optional)

To close a specific tab or pause YouTube, load the browser extension once: Settings → Desktop →
"Chrome / Edge setup" and follow the page (Load unpacked, then the page says **Paired**). Updates load by themselves.

## 7. When something goes wrong

| You see | Do this |
|---|---|
| "Backend unreachable" | Start START_AGENT_X.cmd again; check `AgentDesk_AI\logs\backend.log` |
| "Local agent ko yeh command clear nahi hui" | Say the app/file name and the action, or start with "AI:" (needs a Groq key) |
| "did not start (autoplay may be blocked)" | Press Play once in the YouTube tab |
| "No number saved for …" | Add "Name: +92…" on the Memory page or say the full number |
| A task says **partially completed** | Some steps worked; the card lists what changed and what can be undone |

Privacy: everything runs on this PC. Only "AI:" requests (with your Groq key) and browser speech recognition
leave the PC. Logs never contain your commands or keys.
