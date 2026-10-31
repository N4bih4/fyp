"""Text normalisation for English, Roman Urdu, Urdu and Hindi commands.

- `detect_language`: script first (Arabic -> ur, Devanagari -> hi), then Roman
  Urdu marker words, else English.
- `numbers_to_digits`: number words in all four languages -> digits
  ("pachas" / "پچاس" / "पचास" / "fifty" -> 50, "twenty five" -> 25).
- `canonical_tokens`: every word or short phrase from the shared lexicon is
  mapped to one canonical token (OPEN, CLOSE, VOLUME, ...). Unknown words are
  kept as written (case preserved) so names, queries and paths survive.
  ASCII typos are corrected with rapidfuzz against the lexicon (>= 86), and
  each correction is recorded so the matcher can lower its confidence.

Paths, URLs and e-mail addresses are never fuzzy-matched or rewritten.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

ARABIC = re.compile(r"[؀-ۿ]")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
PATHLIKE = re.compile(r"^(?:[A-Za-z]:[\\/]|~[\\/]|/|\\\\)|[\\/].*\.\w{1,5}$")
URLLIKE = re.compile(r"^(?:https?://\S+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|pk|in|dev|ai|edu|gov|co)(?:/\S*)?)$", re.I)
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

ROMAN_MARKERS = set(
    "karo kar kardo krdo kro kr do dein dena kholo khol kholna kholdo band bnd mein main pe par ka ki ke ko hai hain "
    "awaz awaaz aawaz roshni barha barhao badha badhao zyada ziada ziyada jyada kam thora thori thoda aur naya naam "
    "banao bana dikhao dhoondo dhundo dhoondho mita chalao chala rok roko dobara laga lagao kitna kitni batao parho "
    "lo le isay ise isko usay doosra dusra pehla wala wali bhejo salam shukriya bilkul poori aadhi kaise ho yeh".split()
)


def detect_language(text: str) -> str:
    if ARABIC.search(text):
        return "ur"
    if DEVANAGARI.search(text):
        return "hi"
    words = re.findall(r"[a-z]+", text.casefold())
    hits = sum(1 for w in words if w in ROMAN_MARKERS)
    return "roman_ur" if hits and (hits >= 2 or hits / max(1, len(words)) >= 0.25) else "en"


# ------------------------------------------------------------------ numbers
_NUMBER_WORDS: dict[str, int] = {}
_EN = {"zero": 0, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
       "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
       "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
       "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_ROMAN = {"ek": 1, "teen": 3, "char": 4, "chaar": 4, "panch": 5, "paanch": 5, "chay": 6, "chhe": 6, "saat": 7,
          "aath": 8, "nau": 9, "das": 10, "dus": 10, "pandrah": 15, "bees": 20, "pachees": 25, "pachis": 25,
          "tees": 30, "paintees": 35, "chalees": 40, "chalis": 40, "paintalees": 45, "pachas": 50, "pachaas": 50,
          "pachpan": 55, "saath": 60, "sath": 60, "painsath": 65, "sattar": 70, "pachattar": 75, "assi": 80,
          "pachasi": 85, "nabbe": 90, "nabe": 90, "pachanve": 95, "sau": 100}
_URDU = {"ایک": 1, "تین": 3, "چار": 4, "پانچ": 5, "چھ": 6, "سات": 7, "آٹھ": 8, "نو": 9, "دس": 10, "پندرہ": 15,
         "بیس": 20, "پچیس": 25, "تیس": 30, "پینتیس": 35, "چالیس": 40, "پینتالیس": 45, "پچاس": 50, "پچپن": 55,
         "ساٹھ": 60, "پینسٹھ": 65, "ستر": 70, "پچھتر": 75, "اسی": 80, "پچاسی": 85, "نوے": 90, "پچانوے": 95, "سو": 100}
_HINDI = {"एक": 1, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
          "पंद्रह": 15, "बीस": 20, "पच्चीस": 25, "तीस": 30, "पैंतीस": 35, "चालीस": 40, "पैंतालीस": 45,
          "पचास": 50, "पचपन": 55, "साठ": 60, "पैंसठ": 65, "सत्तर": 70, "पचहत्तर": 75, "अस्सी": 80,
          "पचासी": 85, "नब्बे": 90, "पचानवे": 95, "सौ": 100}
for table in (_EN, _ROMAN, _URDU, _HINDI):
    _NUMBER_WORDS.update(table)


def numbers_to_digits(text: str) -> str:
    """Replace number words with digits; English tens+units are combined."""
    words = text.split()
    out: list[str] = []
    i = 0
    while i < len(words):
        word = words[i]
        key = unicodedata.normalize("NFKC", word).casefold().replace("़", "").strip(".,!?")
        if key in _TENS and i + 1 < len(words):
            unit = words[i + 1].casefold().strip(".,!?")
            if unit in _EN and 1 <= _EN[unit] <= 9:
                out.append(str(_TENS[key] + _EN[unit]))
                i += 2
                continue
        if key in _NUMBER_WORDS:
            out.append(str(_NUMBER_WORDS[key]))
        else:
            out.append(word)
        i += 1
    return " ".join(out)


# ------------------------------------------------------------------ lexicon
# canonical token -> surface forms (single words or short phrases).
LEXICON: dict[str, str] = {
    "OPEN": "open launch start kholo khol kholna kholdo kholiye open-karo اوپن کھولو کھول کھولنا کھولیں ओपन खोलो खोल खोलना",
    "RUN": "chala chalao chalaa چلا چلاؤ چلادو चला चलाओ",
    "CLOSE": "close band bnd bandh بند کلوز बंद क्लोज",
    "ON": "on enable chalu laga lagao لگا لگاؤ آن ऑन चालू लगा लगाओ",
    "OFF": "off disable آف ऑफ",
    "UP": "up increase raise louder barha barhao badha badhao zyada ziada ziyada jyada zada more بڑھا بڑھاؤ زیادہ بڑھائیں बढ़ाओ बढ़ा ज्यादा ज़्यादा",
    "DOWN": "down decrease lower reduce dim kam km ghatao ghata less کم گھٹاؤ कम घटाओ",
    "MUTE": "mute silent میوٹ म्यूट",
    "UNMUTE": "unmute انمیوٹ अनम्यूट",
    "MAX": "max maximum full poori puri پوری पूरी",
    "HALF": "half aadhi adhi آدھی आधी",
    "GET": "kitna kitni status batao what's whats current level کتنا کتنی کتنا ہے कितना कितनी",
    "VOLUME": "volume awaz awaaz aawaz sound audio آواز والیوم وولیوم आवाज वॉल्यूम वाल्यूम",
    "BRIGHTNESS": "brightness roshni برائٹنس روشنی ब्राइटनेस",
    "BLUETOOTH": "bluetooth بلوٹوتھ ब्लूटूथ",
    "WIFI": "wifi وائی-فائی وائیفائی वाईफाई",
    "DARK": "dark ڈارک डार्क",
    "LIGHT": "light لائٹ लाइट",
    "MODE": "mode theme موڈ मोड",
    "SETTINGS": "settings setting سیٹنگز سیٹنگ سیٹنگس सेटिंग्स सेटिंग",
    "DISPLAY": "display ڈسپلے डिस्प्ले",
    "LOCKSCREEN": "lockscreen lock-screen لاک-اسکرین لاک-سکرین लॉक-स्क्रीन",
    "UPDATE": "update اپڈیٹ अपडेट",
    "WINDOWS": "windows ونڈوز विंडोज",
    "FOLDER": "folder directory فولڈر फोल्डर फ़ोल्डर",
    "FILE": "file فائل फाइल फ़ाइल",
    "WINDOW": "window ونڈو विंडो",
    "TAB": "tab tabs ٹیب टैब",
    "VIDEO": "video ویڈیو वीडियो",
    "PAUSE": "pause stop rok roko ruko روک روکو रोक रोको",
    "RESUME": "resume dobara دوبارہ दोबारा",
    "PLAY": "play پلے प्ले",
    "SEARCH": "search google look-up سرچ सर्च",
    "FIND": "find dhoondo dhundo dhoondho talash locate ڈھونڈو ढूंढो",
    "SHOW": "show list dikhao دکھاؤ दिखाओ",
    "DELETE": "delete remove mita mitao erase ڈیلیٹ مٹا डिलीट मिटा",
    "COPY": "copy کاپی कॉपी",
    "MOVE": "move موو मूव",
    "RENAME": "rename",
    "NAME": "naam نام नाम called named",
    "CREATE": "create make banao bana بناؤ بنا बनाओ बना",
    "NEW": "new naya نیا नया",
    "READ": "read parho padho پڑھو पढ़ो",
    "WRITE": "write overwrite likho لکھو लिखो",
    "ZIP": "zip compress",
    "EXTRACT": "extract unzip",
    "SCREENSHOT": "screenshot اسکرین-شاٹ سکرین-شاٹ स्क्रीनशॉट",
    "TRASH": "trash recycle ٹریش ट्रैश",
    "DOWNLOAD": "download ڈاؤن-لوڈ डाउनलोड",
    "INSTALL": "install انسٹال इंस्टॉल",
    "EMAIL": "email e-mail ای-میل ईमेल",
    "MESSAGE": "message msg پیغام میسج मैसेज",
    "SEND": "send bhejo bhej بھیجو भेजो",
    "FORMAT": "format فارمیٹ फॉर्मेट",
    "DRIVE": "drive ڈرائیو ड्राइव",
    "COMMAND": "command",
    "MUSIC": "music song songs gaana gana gaane track گانا گانے موسیقی गाना गाने संगीत",
    "NEXT": "next agla agli skip اگلا اگلی अगला अगली",
    "PREVIOUS": "previous pichla pichli پچھلا پچھلی पिछला पिछली",
    "MINIMIZE": "minimize minimise chota chhota chhota-kar چھوٹا छोटा",
    "MAXIMIZE": "maximize maximise full-screen fullscreen بڑا-کرو बड़ा-करो",
    "FOCUS": "switch-to focus bring-up samne aage سامنے आगे",
    "AND": "and aur اور और",
    "IN": "in mein pe par into inside میں پر में पर",
    "IT": "it this that isay ise isko usay usko اسے اس-کو इसे इसको उसे",
    "FIRST": "first pehla pehli پہلا پہلی पहला पहली 1st",
    "SECOND": "second doosra dusra doosri دوسرا دوسری दूसरा दूसरी 2nd",
    "THIRD": "third teesra تیسرا तीसरा 3rd",
    "WALA": "one wala wali والا والی वाला वाली",
    "BIT": "bit little thora thori thoda thodi تھوڑا تھوڑی थोड़ा थोड़ी",
    "PERCENT": "percent percentage % فیصد پرسنٹ प्रतिशत",
    "GREETING": "hello hi hey salam namaste السلام-علیکم سلام नमस्ते",
    "THANKS": "thanks thank shukriya شکریہ धन्यवाद",
    "HOWAREYOU": "kaise-ho how-are-you",
    "TO": "to",
    "WHERE": "where kahan کہاں कहाँ",
    "WHAT": "what kya کیا क्या",
    "DESKTOP": "desktop ڈیسک-ٹاپ डेस्कटॉप",
    "DOCUMENTS": "documents docs ڈاکومنٹس डॉक्यूमेंट्स",
    "DOWNLOADS": "downloads ڈاؤن-لوڈز ڈاونلوڈز डाउनलोड्स",
    "SCREEN": "screen اسکرین سکرین स्क्रीन",
    "CONTENTS": "contents",
    "INCLUDING": "including",
    "APPROVAL": "approval approved confirmation ask",
}

# Names that map straight to a canonical app or site value.
APP_WORDS: dict[str, str] = {
    "notepad": "notepad", "notpad": "notepad", "نوٹ-پیڈ": "notepad", "نوٹپیڈ": "notepad", "नोटपैड": "notepad", "नोट-पैड": "notepad",
    "chrome": "chrome", "google-chrome": "chrome", "کروم": "chrome", "क्रोम": "chrome",
    "calculator": "calc", "calc": "calc", "کیلکولیٹر": "calc", "कैलकुलेटर": "calc",
    "vs-code": "visual studio code", "vscode": "visual studio code", "visual-studio-code": "visual studio code",
    "وی-ایس-کوڈ": "visual studio code", "वी-एस-कोड": "visual studio code",
    "word": "word", "microsoft-word": "word", "ms-word": "word", "ورڈ": "word", "वर्ड": "word",
    "excel": "excel", "microsoft-excel": "excel", "ایکسل": "excel", "एक्सेल": "excel",
    "powerpoint": "powerpoint", "ppt": "powerpoint",
    "explorer": "explorer", "file-explorer": "explorer", "windows-explorer": "explorer",
    "powershell": "powershell", "power-shell": "powershell", "پاور-شیل": "powershell", "پاورشیل": "powershell", "पावरशेल": "powershell", "पावर-शेल": "powershell",
    "edge": "microsoft edge", "microsoft-edge": "microsoft edge", "intellij": "intellij", "cursor": "cursor",
}
SITE_WORDS: dict[str, str] = {
    "youtube": "youtube", "یوٹیوب": "youtube", "यूट्यूब": "youtube",
    "gmail": "gmail", "جی-میل": "gmail", "जीमेल": "gmail",
    "whatsapp": "whatsapp", "واٹس-ایپ": "whatsapp", "واٹساپ": "whatsapp", "व्हाट्सएप": "whatsapp", "whatsapp-web": "whatsapp",
    "chatgpt": "chatgpt", "chat-gpt": "chatgpt", "چیٹ-جی-پی-ٹی": "chatgpt",
    "google-drive": "google drive", "گوگل-ڈرائیو": "google drive", "गूगल-ड्राइव": "google drive",
}
# Known package names that people say in Urdu/Hindi script.
PACKAGE_WORDS: dict[str, str] = {
    "وی-ایل-سی": "vlc", "वीएलसी": "vlc", "वी-एल-सी": "vlc", "زوم": "zoom", "ज़ूम": "zoom", "जूम": "zoom",
    "vlc": "vlc", "zoom": "zoom", "spotify": "spotify", "telegram": "telegram", "notepad++": "notepad++",
}

FILLER = set(
    "please plz pls kindly zara can could would you for me my mera meri mere the a an ko ka ki ke kar karo kardo "
    "krdo kro kr karna karein kariye do dein dena de dijiye ji sa si yeh ye now right of for-me just bilkul hai lo le "
    "hain se pc computer laptop is are am be ho jaye پلیز ذرا میرا میری میرے مجھے کر کرو دو دیں کا کی کے کو ہے "
    "ہیں جی پی-سی کمپیوٹر مेरा मेरी मेरे मुझे कर करो दो दीजिए का की के को है हैं जी पीसी जरा ज़रा".split()
)

def _form(text: str) -> str:
    """Lexicon forms get the same NFKC/nukta treatment as user text."""
    return unicodedata.normalize("NFKC", text.replace("-", " ")).replace("\u093c", "").casefold()


_PHRASES: dict[str, str] = {}
for canon, forms in LEXICON.items():
    for form in forms.split():
        _PHRASES[_form(form)] = canon
for table, prefix in ((APP_WORDS, "APP:"), (SITE_WORDS, "SITE:"), (PACKAGE_WORDS, "PKG:")):
    for form, value in table.items():
        _PHRASES.setdefault(_form(form), prefix + value)
FILLER = {_form(w) for w in FILLER}
_MAX_PHRASE = max(len(p.split()) for p in _PHRASES)
# Only distinctive ASCII words take part in typo correction.
_FUZZY_TARGETS = sorted({p for p in _PHRASES if p.isascii() and " " not in p and len(p) >= 5 and not p.isdigit()})

# Spelling variants that are full-text rewrites (multi-word or split words).
_REWRITES = [
    (r"\bvol\s+ume\b", "volume"), (r"\bbright\s+ness\b", "brightness"), (r"\bblue\s+tooth\b", "bluetooth"),
    (r"\bwi[\s-]+fi\b", "wifi"), (r"وائی\s+فائی", "wifi"), (r"वाई\s*फाई", "wifi"), (r"\bun\s+mute\b", "unmute"),
    (r"(?<!\w)ان\s+میوٹ(?!\w)", "unmute"), (r"\bk(?:a)?r\s*d(?:o|ou)\b", "kar do"), (r"\bkholdo\b", "khol do"),
    (r"\bkr\s+do\b", "kar do"), (r"\blook\s+up\b", "look-up"), (r"\bwhat\s+is\b", "what's"),
    (r"\bhow\s+are\s+you\b", "how-are-you"), (r"\bkaise\s+ho\b", "kaise-ho"),
    (r"(?<!\w)پی\s+سی(?!\w)", "pc"), (r"(?<!\w)पी\s+सी(?!\w)", "pc"),
]


@dataclass
class Token:
    text: str          # surface text as written (case preserved)
    canon: str         # canonical token, or the lower-cased word when unknown
    fuzzy: bool = False

    @property
    def known(self) -> bool:
        return self.canon.isupper() or ":" in self.canon or self.canon.isdigit()


@dataclass
class Normalized:
    original: str
    language: str
    text: str                       # cleaned text with digits, case preserved
    tokens: list[Token] = field(default_factory=list)
    question: bool = False

    @property
    def canons(self) -> list[str]:
        return [t.canon for t in self.tokens]

    @property
    def fuzzy_count(self) -> int:
        return sum(t.fuzzy for t in self.tokens)


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("़", "")
    text = text.replace("ـ", "")
    for pattern, repl in _REWRITES:
        text = re.sub(pattern, repl, text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _split(text: str) -> list[str]:
    words = []
    for raw in text.split():
        if PATHLIKE.search(raw) or URLLIKE.match(raw.rstrip(",.")) or EMAIL.match(raw.rstrip(",.")):
            words.append(raw.rstrip(","))
            continue
        word = raw.strip(".,!?؟۔।\"'“”()")
        word = word.replace("%", " % ").strip()
        words.extend(w for w in word.split() if w)
        if raw.rstrip("\"'”)").endswith((",", "،")):
            words.append(",")  # clause boundary marker
    return words


def canonical_tokens(text: str, fuzzy_cutoff: float = 86) -> list[Token]:
    words = _split(text)
    tokens: list[Token] = []
    i = 0
    while i < len(words):
        matched = False
        for size in range(min(_MAX_PHRASE, len(words) - i), 0, -1):
            phrase = " ".join(words[i:i + size]).casefold()
            if phrase in _PHRASES:
                tokens.append(Token(" ".join(words[i:i + size]), _PHRASES[phrase]))
                i += size
                matched = True
                break
        if matched:
            continue
        word = words[i]
        low = word.casefold()
        if low.isdigit():
            tokens.append(Token(word, low))
        elif (low.isascii() and low.isalpha() and len(low) >= 5 and not PATHLIKE.search(word)
              and low not in FILLER):
            hit = process.extractOne(low, _FUZZY_TARGETS, scorer=fuzz.ratio, score_cutoff=fuzzy_cutoff)
            if hit:
                tokens.append(Token(word, _PHRASES[hit[0]], fuzzy=True))
            else:
                tokens.append(Token(word, low))
        else:
            tokens.append(Token(word, low))
        i += 1
    return tokens


def normalize(text: str) -> Normalized:
    language = detect_language(text)
    question = text.strip().endswith(("?", "؟"))
    cleaned = numbers_to_digits(clean(text))
    return Normalized(original=text, language=language, text=cleaned,
                      tokens=canonical_tokens(cleaned), question=question)
