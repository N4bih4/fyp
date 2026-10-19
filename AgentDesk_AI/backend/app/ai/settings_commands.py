"""Conservative multilingual direct Settings navigation."""
import re
from .base import Plan, PlanAction


def settings_plan(command):
    from .speech_commands import normalize_speech, NEGATIONS
    from .command_language import OPEN, END, LINK, POLITE
    text = normalize_speech(command)
    if any(word in NEGATIONS for word in text.split()):
        return None
    text = re.sub(POLITE, "", text, flags=re.I)
    noun = r"(?:settings?|سیٹنگز|سیٹنگ|سیٹنگس|सेटिंग्स|सेटिंग)"
    # Permit bare page requests such as 'Windows Update settings'.
    patterns = [rf"{OPEN}\s+(.+?){END}", rf"(.+?)\s+{OPEN}(?:\s+do|{END})", r"(.+)"]
    aliases = {
        "": "root", "pc": "root", "windows": "root", "window": "root",
        "display": "display", "screen": "display", "brightness": "display", "اسکرین": "display", "سکرین": "display", "स्क्रीन": "display",
        "sound": "sound", "audio": "sound", "volume": "sound",
        "bluetooth": "bluetooth", "بلوٹوتھ": "bluetooth", "ब्लूटूथ": "bluetooth",
        "wifi": "wifi", "wi fi": "wifi", "وائی فائی": "wifi", "वाई फाई": "wifi",
        "lock screen": "lockscreen", "lockscreen": "lockscreen", "lock": "lockscreen", "لاک سکرین": "lockscreen", "लॉक स्क्रीन": "lockscreen",
        "windows update": "windowsupdate", "window update": "windowsupdate", "update": "windowsupdate", "ونڈوز اپڈیٹ": "windowsupdate", "विंडोज अपडेट": "windowsupdate",
    }
    for pattern in patterns:
        match = re.fullmatch(pattern, text, re.I)
        if not match:
            continue
        target = match.group(1).strip()
        target = re.sub(rf"{LINK}\s*{noun}$", "", target, flags=re.I).strip()
        if target == match.group(1).strip():
            continue
        page = aliases.get(target)
        if page:
            return Plan(actions=[PlanAction(tool="open_windows_settings", args={"page": page})], note="Windows Settings ka requested page khol raha hoon; API quota use nahi hua.")
    return None
