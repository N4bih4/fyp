"""The coverage matrix: what a person may ask a laptop to do by voice, in three languages, with the tool that should answer and the risk it carries.

One list is the single source for docs/COVERAGE.md and for scripts/coverage_live.py (so the document and the test cannot drift apart).

Row fields
  id      stable name
  group   apps | windows | files | browser | youtube | settings | control_panel | volume | device | media | mail | coding | install | info | ui | talk
  en/ru/hi  the spoken sentence in English, Roman Urdu and Hindi (Devanagari, as Whisper writes it)
  tools   the tool names that count as a right plan (any one of them)
  risk    the risk the plan must carry: low | medium | high   (a plan with LOWER risk than this fails the check: nothing risky may run silently)
  live    how the live run treats it:
            "run"      executed on this PC and verified (only harmless, or undone straight afterwards)
            "approval" executed up to the approval card and then REJECTED: proves the plan and that it asks first; nothing is changed
            "no"       never run here (power, uninstall, send): only the routing check applies
  undo    a spoken sentence that puts a live change back (volume, brightness, theme ...)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Row:
    id: str
    group: str
    en: str
    ru: str
    hi: str
    tools: tuple[str, ...]
    risk: str = "low"
    live: str = "run"
    undo: str = ""


R = Row
ROWS: list[Row] = [
    # ---------------------------------------------------------------- apps
    R("app_open_notepad", "apps", "open notepad", "notepad kholo", "नोटपैड खोलो", ("open_application",)),
    R("app_open_calculator", "apps", "open calculator", "calculator kholo", "कैलकुलेटर खोलो", ("open_application",)),
    R("app_open_paint", "apps", "open paint", "paint kholo", "पेंट खोलो", ("open_application",)),
    R("app_open_explorer", "apps", "open file explorer", "file explorer kholo", "फ़ाइल एक्सप्लोरर खोलो", ("open_application", "explorer_navigate")),
    R("app_open_task_manager", "apps", "open task manager", "task manager kholo", "टास्क मैनेजर खोलो", ("open_application", "open_windows_settings")),
    R("app_open_word", "apps", "open word", "word kholo", "वर्ड खोलो", ("open_application",), live="no"),
    R("app_open_vscode", "apps", "open vs code", "vs code kholo", "वीएस कोड खोलो", ("open_application",), live="no"),
    R("app_close_notepad", "apps", "close notepad", "notepad band karo", "नोटपैड बंद करो", ("control_desktop",), risk="high", live="no"),
    R("app_switch", "apps", "switch to chrome", "chrome pe jao", "क्रोम पर जाओ", ("control_desktop", "ui_act", "open_application"), risk="low", live="no"),
    R("app_list_windows", "apps", "what windows are open", "kaun si windows khuli hain", "कौन सी विंडो खुली हैं", ("control_desktop",), risk="low", live="no"),
    # ---------------------------------------------------------------- windows
    R("win_minimize", "windows", "minimize this window", "yeh window chhoti karo", "यह विंडो छोटी करो", ("ui_act", "control_desktop"), risk="low", live="no"),
    R("win_maximize", "windows", "maximize the window", "window bari karo", "विंडो बड़ी करो", ("ui_act", "control_desktop"), risk="low", live="no"),
    R("win_show_desktop", "windows", "show desktop", "desktop dikhao", "डेस्कटॉप दिखाओ", ("ui_act", "control_desktop"), risk="low", live="no"),
    R("win_close_window", "windows", "close this window", "yeh window band karo", "यह विंडो बंद करो", ("control_desktop",), risk="high", live="approval"),
    # ---------------------------------------------------------------- files
    R("file_open_downloads", "files", "open downloads", "downloads kholo", "डाउनलोड खोलो", ("open_folder", "explorer_navigate")),
    R("file_open_documents", "files", "open documents folder", "documents folder kholo", "डॉक्यूमेंट्स फ़ोल्डर खोलो", ("open_folder", "explorer_navigate")),
    R("file_open_desktop", "files", "open desktop folder", "desktop folder kholo", "डेस्कटॉप फ़ोल्डर खोलो", ("open_folder", "explorer_navigate")),
    R("file_open_drive", "files", "open C drive", "C drive kholo", "सी ड्राइव खोलो", ("explorer_navigate", "open_folder")),
    R("file_list_downloads", "files", "what is in my downloads", "downloads mein kya hai", "डाउनलोड में क्या है", ("list_folder",)),
    R("file_find", "files", "find my resume file", "mera resume file dhundo", "मेरी रिज्यूमे फ़ाइल ढूंढो", ("find_files", "find_paths")),
    R("file_create_folder", "files", "create a folder called coverage test on desktop", "desktop pe coverage test naam ka folder banao",
      "डेस्कटॉप पर कवरेज टेस्ट नाम का फ़ोल्डर बनाओ", ("create_folder",), risk="medium", live="approval"),
    R("file_copy", "files", "copy report.txt to documents", "report.txt ko documents mein copy karo", "report.txt को डॉक्यूमेंट्स में कॉपी करो", ("copy_file",), risk="medium", live="approval"),
    R("file_move", "files", "move report.txt to desktop", "report.txt ko desktop pe move karo", "report.txt को डेस्कटॉप पर ले जाओ", ("move_file",), risk="medium", live="approval"),
    R("file_rename", "files", "rename report.txt to final.txt", "report.txt ka naam final.txt karo", "report.txt का नाम final.txt करो", ("rename_file",), risk="medium", live="approval"),
    R("file_delete", "files", "delete report.txt", "report.txt delete karo", "report.txt डिलीट करो", ("delete_file",), risk="high", live="approval"),
    R("file_read", "files", "read notes.txt", "notes.txt parho", "notes.txt पढ़ो", ("read_text_file",), live="no"),
    R("file_write", "files", "write hello into note.txt", "note.txt mein hello likho", "note.txt में hello लिखो", ("write_text_file",), risk="medium", live="no"),
    R("file_zip", "files", "zip my documents folder", "documents folder ko zip karo", "डॉक्यूमेंट्स फ़ोल्डर को ज़िप करो", ("compress_folder",), risk="medium", live="approval"),
    R("file_trash", "files", "show what I deleted", "jo delete kiya woh dikhao", "जो डिलीट किया वह दिखाओ", ("list_trash",)),
    R("file_summarise", "files", "summarise report.pdf", "report.pdf ka khulasa do", "report.pdf का सारांश दो", ("summarise_file", "make_document"), live="no"),
    # ---------------------------------------------------------------- browser
    R("web_open_youtube", "browser", "open youtube", "youtube kholo", "यूट्यूब खोलो", ("open_url",)),
    R("web_open_github", "browser", "open github", "github kholo", "गिटहब खोलो", ("open_url",)),
    R("web_open_gmail", "browser", "open gmail", "gmail kholo", "जीमेल खोलो", ("open_url",), live="no"),
    R("web_search", "browser", "search python tutorial on google", "google pe python tutorial search karo", "गूगल पर पाइथन ट्यूटोरियल सर्च करो", ("web_search",)),
    R("web_new_tab", "browser", "open a new tab", "nayi tab kholo", "नया टैब खोलो", ("control_browser", "open_url", "ui_act"), live="no"),
    R("web_close_tab", "browser", "close this tab", "yeh tab band karo", "यह टैब बंद करो", ("control_browser", "control_desktop"), risk="low", live="no"),
    R("web_profile", "browser", "open chrome with the work profile", "chrome mein work profile kholo", "क्रोम में वर्क प्रोफ़ाइल खोलो", ("open_browser_profile",), live="no"),
    R("web_read_page", "browser", "read this page", "yeh page parho", "यह पेज पढ़ो", ("control_browser", "summarise_page"), live="no"),
    R("web_summarise_page", "browser", "summarise this page", "is page ka khulasa do", "इस पेज का सारांश दो", ("summarise_page", "control_browser"), live="no"),
    R("web_history", "browser", "reopen my last closed tab", "pichli band tab dobara kholo", "पिछला बंद टैब फिर खोलो", ("control_browser",), live="no"),
    # ---------------------------------------------------------------- youtube
    R("yt_play", "youtube", "play lofi music on youtube", "youtube pe lofi music chalao", "यूट्यूब पर लोफ़ी म्यूज़िक चलाओ", ("play_youtube_video",), live="no"),
    R("yt_pause", "youtube", "pause the video", "video rok do", "वीडियो रोक दो", ("control_browser", "media_control")),
    R("yt_resume", "youtube", "play the video", "video chalao", "वीडियो चलाओ", ("control_browser", "media_control")),
    R("yt_next", "youtube", "next video", "agli video", "अगला वीडियो", ("control_browser", "media_control")),
    R("yt_skip_ad", "youtube", "skip the ad", "ad skip karo", "विज्ञापन स्किप करो", ("control_browser",)),
    R("yt_seek", "youtube", "skip 10 seconds", "10 second aage karo", "10 सेकंड आगे करो", ("control_browser",)),
    R("yt_speed", "youtube", "set speed to 1.5", "speed 1.5 karo", "स्पीड 1.5 करो", ("control_browser",)),
    R("yt_mute", "youtube", "mute the video", "video ki awaz band karo", "वीडियो की आवाज़ बंद करो", ("control_browser", "manage_system_setting")),
    R("yt_fullscreen", "youtube", "full screen", "full screen karo", "फ़ुल स्क्रीन करो", ("control_browser",)),
    R("yt_now_playing", "youtube", "what is playing", "kya chal raha hai", "क्या चल रहा है", ("control_browser", "media_control")),
    R("yt_like", "youtube", "like this video", "yeh video like karo", "यह वीडियो लाइक करो", ("control_browser",), risk="low", live="no"),
    R("yt_subscribe", "youtube", "subscribe to this channel", "is channel ko subscribe karo", "इस चैनल को सब्सक्राइब करो", ("control_browser",), risk="low", live="no"),
    # ---------------------------------------------------------------- volume / brightness / settings
    R("vol_up", "volume", "turn the volume up", "awaz barhao", "आवाज़ बढ़ाओ", ("manage_system_setting",), risk="low", live="run", undo="awaz kam karo"),
    R("vol_down", "volume", "turn the volume down", "awaz kam karo", "आवाज़ कम करो", ("manage_system_setting",), risk="low", live="run", undo="awaz barhao"),
    R("vol_set", "volume", "set the volume to 30", "volume 30 karo", "वॉल्यूम 30 करो", ("manage_system_setting",), risk="low", live="no"),
    R("vol_mute", "volume", "mute the pc", "pc mute karo", "पीसी म्यूट करो", ("manage_system_setting",), risk="low", live="run", undo="unmute"),
    R("vol_unmute", "volume", "unmute", "unmute karo", "अनम्यूट करो", ("manage_system_setting",), risk="low", live="no"),
    R("bright_up", "volume", "increase brightness", "brightness barhao", "ब्राइटनेस बढ़ाओ", ("manage_system_setting",), risk="low", live="no"),
    R("bright_set", "volume", "set brightness to 60", "brightness 60 karo", "ब्राइटनेस 60 करो", ("manage_system_setting",), risk="low", live="no"),
    R("wifi_off", "settings", "turn wifi off", "wifi band karo", "वाईफाई बंद करो", ("manage_system_setting",), risk="medium", live="no"),
    R("bt_on", "settings", "turn bluetooth on", "bluetooth on karo", "ब्लूटूथ चालू करो", ("manage_system_setting",), risk="medium", live="no"),
    R("theme_dark", "settings", "switch to dark mode", "dark mode lagao", "डार्क मोड लगाओ", ("manage_system_setting",), risk="low", live="no"),
    R("battery", "settings", "how much battery is left", "battery kitni bachi hai", "बैटरी कितनी बची है", ("device_control",), live="run"),
    R("screenshot", "settings", "take a screenshot", "screenshot lo", "स्क्रीनशॉट लो", ("take_screenshot",), risk="medium", live="approval"),
    # ---------------------------------------------------------------- settings pages and the control panel
    R("page_settings", "control_panel", "open settings", "settings kholo", "सेटिंग्स खोलो", ("open_windows_settings",)),
    R("page_display", "control_panel", "open display settings", "display settings kholo", "डिस्प्ले सेटिंग्स खोलो", ("open_windows_settings",)),
    R("page_sound", "control_panel", "open sound settings", "sound settings kholo", "साउंड सेटिंग्स खोलो", ("open_windows_settings",), live="no"),
    R("page_bluetooth", "control_panel", "open bluetooth settings", "bluetooth settings kholo", "ब्लूटूथ सेटिंग्स खोलो", ("open_windows_settings",), live="no"),
    R("page_wifi", "control_panel", "open wifi settings", "wifi settings kholo", "वाईफाई सेटिंग्स खोलो", ("open_windows_settings",), live="no"),
    R("page_update", "control_panel", "open windows update", "windows update kholo", "विंडोज़ अपडेट खोलो", ("open_windows_settings",), live="no"),
    R("page_apps", "control_panel", "open installed apps", "installed apps kholo", "इंस्टॉल्ड ऐप्स खोलो", ("open_windows_settings",)),
    R("page_battery", "control_panel", "open battery settings", "battery settings kholo", "बैटरी सेटिंग्स खोलो", ("open_windows_settings",), live="no"),
    R("page_privacy", "control_panel", "open privacy settings", "privacy settings kholo", "प्राइवेसी सेटिंग्स खोलो", ("open_windows_settings",), live="no"),
    R("page_network", "control_panel", "open network settings", "network settings kholo", "नेटवर्क सेटिंग्स खोलो", ("open_windows_settings",), live="no"),
    R("page_personalise", "control_panel", "open personalization", "personalization kholo", "पर्सनलाइज़ेशन खोलो", ("open_windows_settings",), live="no"),
    R("page_storage", "control_panel", "open storage settings", "storage settings kholo", "स्टोरेज सेटिंग्स खोलो", ("open_windows_settings",), live="no"),
    R("page_default_apps", "control_panel", "open default apps", "default apps kholo", "डिफ़ॉल्ट ऐप्स खोलो", ("open_windows_settings",), live="no"),
    R("page_startup", "control_panel", "open startup apps", "startup apps kholo", "स्टार्टअप ऐप्स खोलो", ("open_windows_settings",), live="no"),
    R("page_about", "control_panel", "open about this pc", "about pc kholo", "इस पीसी के बारे में खोलो", ("open_windows_settings",), live="no"),
    R("page_control_panel", "control_panel", "open control panel", "control panel kholo", "कंट्रोल पैनल खोलो", ("open_windows_settings",)),
    R("page_device_manager", "control_panel", "open device manager", "device manager kholo", "डिवाइस मैनेजर खोलो", ("open_windows_settings",)),
    R("page_network_adapters", "control_panel", "open network connections", "network connections kholo", "नेटवर्क कनेक्शन खोलो", ("open_windows_settings",), live="no"),
    R("page_power_options", "control_panel", "open power options", "power options kholo", "पावर ऑप्शन खोलो", ("open_windows_settings",)),
    R("page_programs", "control_panel", "open programs and features", "programs and features kholo", "प्रोग्राम्स एंड फ़ीचर्स खोलो", ("open_windows_settings",), live="no"),
    R("page_disk_management", "control_panel", "open disk management", "disk management kholo", "डिस्क मैनेजमेंट खोलो", ("open_windows_settings",), live="no"),
    # ---------------------------------------------------------------- device / power
    R("pc_lock", "device", "lock the pc", "pc lock karo", "पीसी लॉक करो", ("device_control",), risk="medium", live="no"),
    R("pc_sleep", "device", "put the pc to sleep", "pc ko sula do", "पीसी को सुला दो", ("device_control",), risk="medium", live="no"),
    R("pc_restart", "device", "restart the pc", "pc restart karo", "पीसी रीस्टार्ट करो", ("device_control",), risk="high", live="no"),
    R("pc_shutdown", "device", "shut down the pc", "pc band karo", "पीसी बंद करो", ("device_control",), risk="high", live="no"),
    R("pc_keep_awake", "device", "keep the pc awake", "pc ko jagaye rakho", "पीसी को जगाए रखो", ("device_control",), risk="low", live="no"),
    # ---------------------------------------------------------------- media keys
    R("media_pause", "media", "pause the music", "music rok do", "म्यूज़िक रोक दो", ("media_control", "control_browser")),
    R("media_next", "media", "next song", "agla gana", "अगला गाना", ("media_control", "control_browser"), live="no"),
    # ---------------------------------------------------------------- mail and chat
    R("mail_write", "mail", "write an email to ali", "ali ko email likho", "अली को ईमेल लिखो", ("compose_email",), risk="medium", live="no"),
    R("chat_whatsapp", "mail", "message ahmed on whatsapp I am late", "whatsapp pe ahmed ko likho main late hoon", "व्हाट्सएप पर अहमद को लिखो मैं लेट हूँ", ("whatsapp_open_chat",), risk="medium", live="no"),
    # ---------------------------------------------------------------- coding apps and terminal
    R("code_terminal", "coding", "open a terminal", "terminal kholo", "टर्मिनल खोलो", ("open_terminal", "open_application")),
    R("code_git_status", "coding", "run git status", "git status chalao", "git status चलाओ", ("run_terminal_command",), risk="low", live="no"),
    R("code_agent", "coding", "ask claude to fix the login bug", "claude se kaho login bug theek kare", "क्लॉड से कहो लॉगिन बग ठीक करे", ("drive_coding_agent",), risk="medium", live="no"),
    # ---------------------------------------------------------------- install / uninstall
    R("pkg_install", "install", "install vlc", "vlc install karo", "वीएलसी इंस्टॉल करो", ("winget_install", "application_package"), risk="high", live="no"),
    R("pkg_uninstall", "install", "uninstall vlc", "vlc uninstall karo", "वीएलसी अनइंस्टॉल करो", ("winget_uninstall",), risk="high", live="no"),
    # ---------------------------------------------------------------- information
    R("info_answer", "info", "what is the capital of australia", "australia ka capital kya hai", "ऑस्ट्रेलिया की राजधानी क्या है", ("web_answer",), live="no"),
    R("info_remember", "info", "remember my locker number is 42", "yaad rakho mera locker number 42 hai", "याद रखो मेरा लॉकर नंबर 42 है", ("memory_remember",), live="no"),
    R("info_recall", "info", "what is my locker number", "mera locker number kya hai", "मेरा लॉकर नंबर क्या है", ("memory_recall",), live="no"),
    R("info_document", "info", "make a study plan for physics", "physics ka study plan banao", "फ़िज़िक्स का स्टडी प्लान बनाओ", ("make_document",), risk="medium", live="no"),
    # ---------------------------------------------------------------- screen control
    R("ui_click", "ui", "click the save button", "save button dabao", "सेव बटन दबाओ", ("ui_act", "screen_act"), risk="medium", live="no"),
    R("ui_type", "ui", "type hello world", "hello world likho", "hello world टाइप करो", ("ui_act",), risk="medium", live="no"),
]

GROUPS = {
    "apps": "Apps", "windows": "Windows", "files": "Files and folders", "browser": "Browser", "youtube": "YouTube", "volume": "Volume and brightness",
    "settings": "Settings (Wi-Fi, Bluetooth, theme, battery, screenshot)", "control_panel": "Settings pages and the Control Panel", "device": "Power and device",
    "media": "Media keys", "mail": "Mail and chat", "coding": "Coding apps and terminal", "install": "Install and uninstall", "info": "Questions, memory, documents",
    "ui": "Any app on screen",
}
