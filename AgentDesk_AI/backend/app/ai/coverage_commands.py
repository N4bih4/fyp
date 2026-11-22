"""Table-driven spoken commands that the older parsers missed, found by the coverage matrix (docs/COVERAGE.md, backend/scripts/coverage_live.py).

Every rule turns one clear sentence (English, Roman Urdu, Hindi in Devanagari) into ONE plan for a tool that already exists; the tool still decides the risk
and asks for approval. A rule fires only for a short, whole sentence, never for a fragment inside a longer one.

  settings pages and the Control Panel   "open display settings", "control panel kholo", "device manager"      -> open_windows_settings
  known folders                          "downloads kholo", "डाउनलोड खोलो"                                       -> explorer_navigate
  websites                               "github kholo", "गिटहब खोलो", "new tab"                                  -> open_url
  closed tab                             "reopen my last closed tab"                                             -> control_browser reopen
  windows                                "what windows are open"                                                  -> control_desktop inspect
  media keys                             "pause the music", "agla gana"                                           -> media_control
  theme                                  "dark mode lagao"                                                        -> manage_system_setting
  PC in Hindi                            "पीसी लॉक करो" ...                                                      -> device_control
  YouTube in Hindi / Roman Urdu          "अगला वीडियो", "यूट्यूब पर ... चलाओ", "speed 1.5 karo"                  -> control_browser / play_youtube_video
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Plan, PlanAction

NOTE = "Local agent ne plan tayyar kiya; cloud API use nahi hui."
OPEN = r"(?:open|launch|show|go\s+to|kholo|khol\s+do|kholna|dikhao|dikha\s+do|chalao|खोलो|खोल\s+दो|दिखाओ|चलाओ|کھولو|دکھاؤ)"
NOT_A_SETTING_CHANGE = re.compile(r"\b(?:turn|switch|set|increase|decrease|enable|disable|mute|unmute|on|off|chalu|band|barhao|kam|badhao|ghatao)\b|चालू|बंद|बढ़ाओ|कम\s+करो", re.I)


def _plan(tool: str, args: dict) -> Plan:
    return Plan(actions=[PlanAction(tool=tool, args=args)], note=NOTE)


def _clean(text: str) -> str:
    return " ".join(str(text or "").casefold().replace("’", "'").split()).strip(" .!?,;:।۔")


# ------------------------------------------------------------------------------------------------ settings pages
# page -> (words that name it, needs the word "settings"/"सेटिंग" next to it?)
PAGES: list[tuple[str, str, bool]] = [
    ("controlpanel", r"control\s*panel|कंट्रोल\s*पैनल|کنٹرول\s*پینل", False),
    ("devicemanager", r"device\s*manager|डिवाइस\s*मैनेजर", False),
    ("networkconnections", r"network\s*(?:connections|adapters)|नेटवर्क\s*कनेक्शन", False),
    ("poweroptions", r"power\s*options?|पावर\s*ऑप्शन", False),
    ("programsfeatures", r"programs?\s*(?:and|&|n|aur)\s*features?|प्रोग्राम्स?\s*एंड\s*फ़?ीचर्स?", False),
    ("diskmanagement", r"disk\s*management|डिस्क\s*मैनेजमेंट", False),
    ("taskmanager", r"task\s*manager|टास्क\s*मैनेजर", False),
    ("systemproperties", r"system\s*properties|सिस्टम\s*प्रॉपर्टीज़?", False),
    ("windowsupdate", r"windows\s*update|विंडोज़?\s*अपडेट", False),
    ("lockscreen", r"lock\s*screen", True),
    ("security", r"windows\s*security|defender|विंडोज़?\s*सिक्योरिटी", False),
    ("startupapps", r"startup\s*apps?|स्टार्टअप\s*ऐप्स?", False),
    ("defaultapps", r"default\s*apps?|डिफ़?ॉल्ट\s*ऐप्स?", False),
    ("apps", r"installed\s*apps?|apps?\s*(?:and|&)\s*features?|इंस्टॉल्ड\s*ऐप्स?", False),
    ("about", r"about\s*(?:this\s*)?pc|इस\s*पीसी\s*के\s*बारे\s*में|पीसी\s*के\s*बारे\s*में", False),
    ("nightlight", r"night\s*light", True),
    ("bluetooth", r"bluetooth|ब्लूटूथ", True),
    ("wifi", r"wi-?\s*fi|वाई-?\s*फ़?ाई", True),
    ("display", r"display|डिस्प्ले", True),
    ("sound", r"sound|साउंड", True),
    ("battery", r"battery|बैटरी", True),
    ("privacy", r"privacy|प्राइवेसी", True),
    ("network", r"network|नेटवर्क", True),
    ("personalization", r"personali[sz]ation|पर्सनलाइज़?ेशन", False),
    ("storage", r"storage|स्टोरेज", True),
    ("notifications", r"notifications?|नोटिफ़?िकेशन", True),
    ("accounts", r"accounts?|अकाउंट", True),
    ("datetime", r"date\s*(?:and|&)\s*time|time\s*(?:and\s*date)?|तारीख़?\s*और\s*समय", True),
    ("mouse", r"mouse|माउस", True),
    ("printers", r"printers?|प्रिंटर", True),
    ("power", r"power\s*(?:and\s*sleep)?", True),
    ("vpn", r"\bvpn\b", True),
    ("hotspot", r"hotspot|हॉटस्पॉट", True),
    ("language", r"language|भाषा", True),
    ("troubleshoot", r"troubleshoot(?:ing|er)?", False),
    ("recovery", r"recovery", True),
]
SETTINGS_WORD = r"(?:settings?|setting|सेटिंग्स?|سیٹنگز?|setings)"


def settings_plan(text: str) -> Plan | None:
    low = _clean(text)
    if not low or len(low.split()) > 8 or NOT_A_SETTING_CHANGE.search(low):
        return None
    if re.fullmatch(rf"(?:please\s+)?(?:{OPEN}\s+)?(?:windows\s+|pc\s+)?{SETTINGS_WORD}(?:\s+{OPEN})?", low):
        return _plan("open_windows_settings", {"page": "root"})
    for page, words, needs_word in PAGES:
        named = re.search(words, low)
        if not named:
            continue
        has_word = re.search(SETTINGS_WORD, low) is not None
        opened = re.search(OPEN, low) is not None
        if needs_word and not has_word:
            continue
        if not (has_word or opened):
            if needs_word:
                continue
            if len(low.split()) > 4:       # "control panel" said alone is enough; a longer sentence must open something
                continue
        rest = re.sub(words, " ", low)
        rest = re.sub(SETTINGS_WORD, " ", rest)
        rest = re.sub(OPEN, " ", rest)
        rest = re.sub(r"\b(?:the|my|please|a|app|page|window|pe|par|ko|ka|ki|ke|mein|me|jao|karo|kar|do|to|of|for|me|about|this|pc)\b|का|को|की|के|में|पर|करो|कर|दो", " ", rest)
        if rest.strip(" ,.-"):
            continue                        # other words are left over: not a plain request to open that page
        return _plan("open_windows_settings", {"page": page})
    return None


# ------------------------------------------------------------------------------------------------ known folders
FOLDERS = {"downloads": "Downloads", "download": "Downloads", "डाउनलोड": "Downloads", "डाउनलोड्स": "Downloads", "documents": "Documents", "document": "Documents",
           "डॉक्यूमेंट्स": "Documents", "डॉक्युमेंट्स": "Documents", "desktop": "Desktop", "डेस्कटॉप": "Desktop", "pictures": "Pictures", "photos": "Pictures",
           "पिक्चर्स": "Pictures", "music": "Music", "म्यूज़िक": "Music", "videos": "Videos", "वीडियोज़": "Videos", "वीडियोज": "Videos"}


def folder_plan(text: str) -> Plan | None:
    low = _clean(text)
    m = re.fullmatch(rf"(?:please\s+)?(?:{OPEN}\s+)?(?:the\s+|my\s+)?(\S+)(?:\s+(?:folder|फ़ोल्डर|फोल्डर))?(?:\s+{OPEN})?", low)
    if not m or m.group(1) not in FOLDERS or not re.search(OPEN + r"|folder|फ़ोल्डर|फोल्डर", low):
        return None
    if m.group(1) in ("desktop", "डेस्कटॉप") and not re.search(r"folder|फ़ोल्डर|फोल्डर|open|kholo|खोलो", low):
        return None                         # "show desktop" / "desktop dikhao" means the Windows desktop (minimise everything), not the Desktop folder
    path = Path.home() / FOLDERS[m.group(1)]
    return _plan("explorer_navigate", {"path": str(path)}) if path.is_dir() else None


def list_folder_plan(text: str) -> Plan | None:
    """"what is in my downloads", "downloads mein kya hai" -> list_folder (live bug: the cloud agent answered "I don't have access to your Downloads folder")."""
    low = _clean(text)
    names = "|".join(sorted((re.escape(k) for k in FOLDERS), key=len, reverse=True))
    m = (re.fullmatch(rf"(?:please\s+)?(?:what(?:'s|\s+is)\s+in|show\s+(?:me\s+)?(?:what(?:'s|\s+is)\s+in)?|list|what\s+files\s+are\s+in)\s+(?:the\s+|my\s+)?({names})(?:\s+folder)?", low)
         or re.fullmatch(rf"(?:the\s+|my\s+)?({names})\s+(?:folder\s+)?(?:mein|me|main)\s+kya\s+(?:hai|hain)", low)
         or re.fullmatch(rf"({names})\s+(?:में|मे)\s+क्या\s+है", low))
    if not m:
        return None
    path = Path.home() / FOLDERS[m.group(1)]
    return _plan("list_folder", {"path": str(path)}) if path.is_dir() else None


# ------------------------------------------------------------------------------------------------ websites, new tab, closed tab
SITES = {"github": "https://github.com", "गिटहब": "https://github.com", "git hub": "https://github.com", "stackoverflow": "https://stackoverflow.com",
         "stack overflow": "https://stackoverflow.com", "स्टैक ओवरफ़्लो": "https://stackoverflow.com", "daraz": "https://www.daraz.pk", "दराज़": "https://www.daraz.pk",
         "pinterest": "https://www.pinterest.com", "tiktok": "https://www.tiktok.com", "outlook web": "https://outlook.live.com", "google maps": "https://maps.google.com",
         "maps": "https://maps.google.com", "गूगल मैप्स": "https://maps.google.com", "chatgpt": "https://chatgpt.com", "चैटजीपीटी": "https://chatgpt.com"}


def site_plan(text: str) -> Plan | None:
    low = _clean(text)
    if re.fullmatch(rf"(?:please\s+)?(?:{OPEN}\s+)?(?:a\s+)?(?:new\s+tab|nayi\s+tab|naya\s+tab|नया\s+टैब|नई\s+टैब)(?:\s+{OPEN})?", low):
        return _plan("open_url", {"url": "https://www.google.com"})
    m = re.fullmatch(rf"(?:please\s+)?(?:{OPEN}\s+)?(?:the\s+)?(.+?)(?:\s+(?:website|site|वेबसाइट))?(?:\s+{OPEN})?", low)
    if m and m.group(1) in SITES and re.search(OPEN, low):
        return _plan("open_url", {"url": SITES[m.group(1)]})
    if re.fullmatch(r"(?:please\s+)?(?:reopen|restore|open)\s+(?:my\s+|the\s+)?(?:last\s+|previous\s+)?closed\s+tab|(?:pichli|pichhli|last)\s+band\s+(?:ki\s+hui\s+)?tab\s+(?:dobara|phir|wapas)\s+(?:kholo|khol\s+do)|"
                    r"पिछला\s+बंद\s+टैब\s+(?:फिर|दोबारा|वापस)\s+खोलो", low):
        return _plan("control_browser", {"action": "reopen"})
    return None


# ------------------------------------------------------------------------------------------------ windows, media keys, theme
def window_list_plan(text: str) -> Plan | None:
    low = _clean(text)
    if re.fullmatch(r"(?:what|which)\s+windows\s+are\s+(?:open|running)|(?:list|show)\s+(?:my\s+|all\s+)?(?:open\s+)?windows|kaun\s*si\s+windows?\s+khuli\s+hain?|"
                    r"कौन\s*सी\s+विंडो\s+खुली\s+हैं", low):
        return _plan("control_desktop", {"steps": [{"action": "inspect"}]})
    return None


MEDIA = [
    (r"(?:pause|stop)\s+(?:the\s+)?(?:music|song|gana|gaana|audio)|(?:music|gana|gaana|song)\s+(?:rok\s+do|roko|band\s+karo|pause\s+karo)|म्यूज़िक\s+रोक\s+दो|गाना\s+रोक\s+दो", "pause"),
    (r"(?:play|resume)\s+(?:the\s+)?(?:music|song)|(?:music|gana|gaana)\s+(?:chalao|chala\s+do|shuru\s+karo)|म्यूज़िक\s+चलाओ", "play"),
    (r"next\s+(?:song|track)|skip\s+(?:this\s+)?(?:song|track)|agla\s+(?:gana|gaana|song)|अगला\s+गाना", "next"),
    (r"(?:previous|last)\s+(?:song|track)|pichla\s+(?:gana|gaana|song)|पिछला\s+गाना", "previous"),
]


def media_plan(text: str) -> Plan | None:
    low = _clean(text)
    for words, action in MEDIA:
        if re.fullmatch(rf"(?:please\s+)?(?:{words})", low):
            return _plan("media_control", {"action": action})
    return None


def theme_plan(text: str) -> Plan | None:
    low = _clean(text)
    dark = r"(?:switch\s+to\s+|turn\s+on\s+|enable\s+|set\s+)?dark\s+(?:mode|theme)(?:\s+(?:on|lagao|laga\s+do|karo|kar\s+do|chalu\s+karo))?|dark\s+mode\s+on|डार्क\s+मोड(?:\s+(?:लगाओ|चालू\s+करो|ऑन\s+करो))?"
    light = r"(?:switch\s+to\s+|turn\s+on\s+|enable\s+|set\s+)?light\s+(?:mode|theme)(?:\s+(?:on|lagao|laga\s+do|karo|kar\s+do))?|लाइट\s+मोड(?:\s+(?:लगाओ|चालू\s+करो|ऑन\s+करो))?"
    if re.fullmatch(dark, low):
        return _plan("manage_system_setting", {"setting": "theme", "action": "dark"})
    if re.fullmatch(light, low):
        return _plan("manage_system_setting", {"setting": "theme", "action": "light"})
    return None


# ------------------------------------------------------------------------------------------------ the PC and YouTube in Hindi / more Roman Urdu
DEVICE_HI = [
    (r"(?:पीसी|कंप्यूटर|लैपटॉप)\s+(?:को\s+)?लॉक\s+(?:करो|कर\s+दो)", "lock"),
    (r"(?:पीसी|कंप्यूटर|लैपटॉप)\s+(?:को\s+)?(?:सुला\s+दो|स्लीप\s+(?:करो|कर\s+दो))", "sleep"),
    (r"(?:पीसी|कंप्यूटर|लैपटॉप)\s+(?:को\s+)?(?:रीस्टार्ट|रिस्टार्ट)\s+(?:करो|कर\s+दो)", "restart"),
    (r"(?:पीसी|कंप्यूटर|लैपटॉप)\s+(?:को\s+)?(?:बंद\s+(?:करो|कर\s+दो)|शटडाउन\s+(?:करो|कर\s+दो))", "shutdown"),
    (r"(?:पीसी|कंप्यूटर|लैपटॉप)\s+(?:को\s+)?जगाए\s+रखो|pc\s+ko\s+jagaye\s+rakho|(?:laptop|pc|computer)\s+jaga(?:ye|y)?\s+rakho", "keep_awake"),
    (r"(?:पीसी|कंप्यूटर|लैपटॉप)\s+म्यूट\s+(?:करो|कर\s+दो)", "mute"),
]
YT = [
    (r"अगला\s+वीडियो|agli\s+video", {"action": "next"}),
    (r"(?:विज्ञापन|ऐड|ad)\s+स्किप\s+(?:करो|कर\s+दो)|ad\s+skip\s+karo", {"action": "skip_ad"}),
    (r"फ़?ुल\s+स्क्रीन(?:\s+(?:करो|कर\s+दो))?", {"action": "fullscreen"}),
    (r"क्या\s+चल\s+रहा\s+है|kya\s+chal\s+raha\s+hai", {"action": "now_playing"}),
    (r"(?:वीडियो|video)\s+(?:की|ki)\s+(?:आवाज़|awaz|awaaz)\s+(?:बंद|band)\s+(?:करो|karo)", {"action": "mute"}),
    (r"(?:यह|yeh|ye)\s+(?:वीडियो|video)\s+(?:लाइक|like)\s+(?:करो|karo)", {"action": "like"}),
    (r"(?:इस|is)\s+(?:चैनल|channel)\s+(?:को\s+|ko\s+)?(?:सब्सक्राइब|subscribe)\s+(?:करो|karo)", {"action": "subscribe"}),
]


def hindi_commands_plan(text: str) -> Plan | None:
    low = _clean(text)
    for words, action in DEVICE_HI:
        if re.fullmatch(words, low):
            if action == "mute":
                return _plan("manage_system_setting", {"setting": "volume", "action": "mute"})
            return _plan("device_control", {"action": action})
    for words, args in YT:
        if re.fullmatch(words, low):
            return _plan("control_browser", {**args, "target": "youtube"})
    m = re.fullmatch(r"(\d{1,3})\s+(?:सेकंड|second|seconds|sec)\s+(?:आगे|aage)\s+(?:करो|karo)", low)
    if m:
        return _plan("control_browser", {"action": "seek", "target": "youtube", "seconds": int(m.group(1))})
    m = re.fullmatch(r"(?:स्पीड|speed)\s+(\d(?:\.\d+)?)\s+(?:करो|karo)", low)
    if m:
        return _plan("control_browser", {"action": "speed", "target": "youtube", "rate": float(m.group(1))})
    m = re.fullmatch(r"(?:यूट्यूब|youtube)\s+(?:पर|से|pe|par|se)\s+(.+?)\s+(?:चलाओ|चला\s+दो|chalao|chala\s+do|laga\s+do|play\s+karo|sunao|सुनाओ)", low)
    if m and len(m.group(1).split()) <= 8:
        return _plan("play_youtube_video", {"query": m.group(1)})
    if re.fullmatch(r"स्क्रीनशॉट\s+(?:लो|ले\s+लो)", low):
        return _plan("take_screenshot", {})
    return None


def active_window_title() -> str | None:
    """The title of the window in front now (Windows), or None; the assistant's own windows do not count."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
    except Exception:  # noqa: BLE001
        return None
    if not title or re.search(r"agent\s*x|agentdesk|orb", title, re.I):
        return None
    return title


WINDOW_STATE = [
    (r"minimi[sz]e\s+(?:this|the|current)\s+window|minimi[sz]e\s+(?:it|window)|(?:yeh|ye|is)\s+window\s+(?:chhoti|choti|minimize)\s*(?:karo|kar\s+do)?|यह\s+विंडो\s+(?:छोटी|मिनिमाइज़?)\s+करो", "minimize_window"),
    (r"maxi?mi[sz]e\s+(?:this|the|current)\s+window|maxi?mi[sz]e\s+(?:it|window)|(?:yeh|ye|is)?\s*window\s+(?:bari|badi|maximize)\s*(?:karo|kar\s+do)?|विंडो\s+(?:बड़ी|मैक्सिमाइज़?)\s+करो", "maximize_window"),
    (r"close\s+(?:this|the|current)\s+window|(?:yeh|ye|is)\s+window\s+band\s+karo|यह\s+विंडो\s+बंद\s+करो", "close_window"),
]


def window_state_plan(text: str) -> Plan | None:
    low = _clean(text)
    for words, action in WINDOW_STATE:
        if re.fullmatch(rf"(?:please\s+)?(?:{words})", low):
            title = active_window_title()
            if title is None:
                return None                 # nothing safe to point at (or the front window is ours): the cloud planner inspects first
            return _plan("control_desktop", {"target_window": title, "steps": [{"action": action}]})
    return None


def terminal_plan(text: str) -> Plan | None:
    """"open a terminal / PowerShell / command prompt" -> open_terminal (live: it was planned as open_application and asked for approval)."""
    low = _clean(text)
    m = re.fullmatch(rf"(?:please\s+)?(?:{OPEN}\s+)?(?:a\s+|the\s+|new\s+)?(terminal|windows\s+terminal|command\s+prompt|cmd|power\s*shell|टर्मिनल|पावरशेल|पावरशेल|कमांड\s+प्रॉम्प्ट)(?:\s+window)?(?:\s+{OPEN})?", low)
    if not m or not re.search(OPEN, low):
        return None
    word = m.group(1)
    shell = "powershell" if re.search(r"power|पावर", word) else ("cmd" if re.search(r"command|cmd|कमांड", word) else "terminal")
    return _plan("open_terminal", {"shell": shell})


def coverage_plan(text: str) -> Plan | None:
    """The first rule that understands the whole sentence, or None."""
    for rule in (settings_plan, list_folder_plan, folder_plan, site_plan, window_list_plan, window_state_plan, terminal_plan, media_plan, theme_plan, hindi_commands_plan):
        plan = rule(text)
        if plan is not None:
            return plan
    return None
