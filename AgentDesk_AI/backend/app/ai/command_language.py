"""Translate command grammar only; preserve user file paths and target names."""
import re

FOLDER = r"(?:folder|فولڈر|فولدر|फोल्डर|फ़ोल्डर)"
FILE = r"(?:file|فائل|फाइल|फ़ाइल)"
APP = r"(?:app|application|ایپ|ایپلیکیشن|ऐप|एप्लीकेशन|एप्लिकेशन)"
OPEN = r"(?:open|اوپن|کھول|کھولو|کھولنا|ओपन|खोल|खोलो|kholo|khol)"
CLOSE = r"(?:close|کلوز|بند|क्लोज|बंद|band)"
DELETE = r"(?:delete|ڈیلیٹ|ڈلیٹ|حذف|डिलीट|डिलीट|delete)"
END = r"(?:\s+(?:kar\s+do|kar\s+dein|karo|کر\s+دو|کر\s+دیں|کرو|کرنا|دو|کریں|کر\s+دیجیے|कर\s+दो|करो|कर\s+दीजिए|दो))?"
LINK = r"(?:\s+(?:ka|ki|ke|کا|کی|کے|का|की|के))?"
POLITE = r"^(?:(?:please|zara|meri|mera|mere|پلیز|ذرا|میرا|میری|میرے|براہ\s+کرم|मेरी|मेरा|मेरे|जरा|प्लीज)\s+)+"


def command_grammar(command: str) -> str:
    """Return canonical grammar or the original request if no full rule matches."""
    raw = command.strip().rstrip("۔।!?")
    # Do not strip or rewrite tokens inside explicit filesystem paths.
    if re.search(r"(?:[A-Za-z]:[\\/]|~/|^/|^\\\\)", raw):
        return raw
    text = re.sub(POLITE, "", raw, flags=re.IGNORECASE)
    for kind, noun in (("folder", FOLDER), ("file", FILE), ("app", APP)):
        patterns = [
            rf"(.+?){LINK}\s+{noun}(?:\s+(?:ان|on|آن))?\s+{OPEN}{END}",
            rf"{noun}\s+(.+?){LINK}\s+{OPEN}{END}",
            rf"{OPEN}\s+(.+?){LINK}\s+{noun}{END}",
            rf"{OPEN}\s+{noun}\s+(.+?){END}",
        ]
        for pattern in patterns:
            match = re.fullmatch(pattern, text, re.IGNORECASE)
            if match:
                return f"open {kind} {match.group(1).strip()}"
        if kind != "app":
            for pattern in (rf"(.+?){LINK}\s+{noun}\s+{DELETE}{END}", rf"{noun}\s+(.+?)\s+{DELETE}{END}", rf"{DELETE}\s+{noun}\s+(.+?){END}"):
                match = re.fullmatch(pattern, text, re.IGNORECASE)
                if match:
                    return f"delete {kind} {match.group(1).strip()}"
    match = re.fullmatch(rf"(.+?)(?:\s+{APP})?\s+{CLOSE}{END}", text, re.IGNORECASE)
    if match:
        return "close " + match.group(1).strip()
    match = re.fullmatch(rf"(.+?)\s+{OPEN}{END}", text, re.IGNORECASE)
    if match:
        # With no folder/file noun, ask app discovery to resolve the named app.
        return "open app " + match.group(1).strip()
    match = re.fullmatch(rf"{OPEN}\s+(.+?){END}", text, re.IGNORECASE)
    if match:
        return "open app " + match.group(1).strip()
    return raw


TARGET_ALIASES = {
    "نوٹ پیڈ": "notepad", "نوٹپیڈ": "notepad", "नोटपैड": "notepad", "नोट पैड": "notepad",
    "کروم": "chrome", "گوگل کروم": "chrome", "क्रोम": "chrome", "गूगल क्रोम": "chrome",
    "واٹس ایپ": "whatsapp", "واٹساپ": "whatsapp", "व्हाट्सएप": "whatsapp", "व्हाट्सएप डेस्कटॉप": "whatsapp",
    "وی ایس کوڈ": "visual studio code", "ویژول اسٹوڈیو کوڈ": "visual studio code", "वी एस कोड": "visual studio code",
    "ڈاؤن لوڈز": "Downloads", "ڈاونلوڈز": "Downloads", "डाउनलोड्स": "Downloads",
    "ڈاکومنٹس": "Documents", "डॉक्यूमेंट्स": "Documents", "ڈیسک ٹاپ": "Desktop", "डेस्कटॉप": "Desktop",
    "یوٹیوب": "youtube", "यूट्यूब": "youtube",
}


def known_target(name: str) -> str:
    return TARGET_ALIASES.get(name.strip(), name.strip())


def search_name_key(name: str) -> str:
    """Limited bilingual aliases for discovery only, never executable paths."""
    aliases = {"semester": "semester", "sem": "semester", "سمسٹر": "semester", "سیمسٹر": "semester", "सेमेस्टर": "semester",
               "six": "6", "sixth": "6", "6th": "6", "سکس": "6", "سک": "6", "چھٹا": "6", "छठा": "6",
               "lecture": "lecture", "لیکچر": "lecture", "लेक्चर": "lecture", "lab": "lab", "لیب": "lab", "लैब": "lab"}
    from .speech_commands import normalize_speech
    words = normalize_speech(name).split()
    return "".join(aliases.get(word, word) for word in words)
