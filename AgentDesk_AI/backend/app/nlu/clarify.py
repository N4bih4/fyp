"""When nothing could plan a command: ONE specific question naming the best guess, never a bare "say it again".

The generic "didn't understand" line is kept for an empty or noise transcript only (voice/responses.py `not_understood`).
"""
from __future__ import annotations

import re

from ..voice.langdetect import reply_language

_Q = {
    "youtube": {"en": "Do you want me to play something on YouTube? Which song or artist?",
                "roman": "Kya main YouTube par kuch chalaun? Kaun sa gana ya artist?",
                "ur": "کیا میں یوٹیوب پر کچھ چلاؤں؟ کون سا گانا یا فنکار؟",
                "hi": "क्या मैं YouTube पर कुछ चलाऊँ? कौन सा गाना या कलाकार?"},
    "open": {"en": "Which app, folder or website should I open?",
             "roman": "Kaun si app, folder ya website kholun?",
             "ur": "کون سی ایپ، فولڈر یا ویب سائٹ کھولوں؟",
             "hi": "कौन सा ऐप, फ़ोल्डर या वेबसाइट खोलूँ?"},
    "file": {"en": "Which file or folder do you mean? Tell me its name.",
             "roman": "Kaun si file ya folder? Uska naam batayein.",
             "ur": "کون سی فائل یا فولڈر؟ اس کا نام بتائیں۔",
             "hi": "कौन सी फ़ाइल या फ़ोल्डर? उसका नाम बताइए।"},
    "mail": {"en": "Who should the e-mail go to, and what should it say?",
             "roman": "Email kisko bhejni hai, aur usme kya likhna hai?",
             "ur": "ای میل کس کو بھیجنی ہے اور اس میں کیا لکھنا ہے؟",
             "hi": "ईमेल किसे भेजना है और उसमें क्या लिखना है?"},
    "system": {"en": "Which setting do you want to change, and to what value?",
               "roman": "Kaun si setting badalni hai, aur kitni?",
               "ur": "کون سی سیٹنگ بدلنی ہے اور کتنی؟",
               "hi": "कौन सी सेटिंग बदलनी है और कितनी?"},
    "generic": {"en": "I'm not sure what to do with that. Do you want me to open something, find a file, play music or search the web?",
                "roman": "Mujhe pakka nahi pata kya karna hai. Kuch kholun, file dhoondun, gana chalaun ya web par search karun?",
                "ur": "مجھے یقین نہیں کہ کیا کرنا ہے۔ کچھ کھولوں، فائل ڈھونڈوں، گانا چلاؤں یا ویب پر تلاش کروں؟",
                "hi": "मुझे पक्का नहीं पता क्या करना है। कुछ खोलूँ, फ़ाइल ढूँढूँ, गाना चलाऊँ या वेब पर खोजूँ?"},
}
_RULES = [
    ("youtube", r"youtube|\byt\b|music|song|gana|gaana|gane|play|chala|یوٹیوب|گان|गाना|म्यूज़िक"),
    ("mail", r"e-?mail|mail\b|ای میل|ईमेल"),
    ("file", r"\bfile|folder|document|download|فائل|فولڈر|फ़ाइल|फोल्डर"),
    ("system", r"volume|brightness|wi-?fi|bluetooth|dark mode|battery|awaz|aawaz|آواز|वॉल्यूम"),
    ("open", r"\bopen\b|kholo|khol\b|launch|start\b|کھولو|खोल"),
]


def guess_key(command: str) -> str:
    text = command.casefold()
    for key, pattern in _RULES:
        if re.search(pattern, text):
            return key
    return "generic"


def question(command: str, setting: str | None = None) -> str:
    """A short question in the language the user spoke (the setting only decides when the sentence is too short to tell)."""
    return _Q[guess_key(command)][reply_language(command, setting)]


CORRECTION = re.compile(
    r"(?i)^\s*(?:no\b|nope\b|not (?:that|this|only|just)|i (?:say|said|meant|mean|told)|i say\b|actually\b|wrong\b|instead\b|nahi\b|nahin\b|nai\b|maine\b|mera matlab|galat\b|"
    r"نہیں|میں نے|غلط|नहीं|मैंने|गलत)|\b(?:not only|not just|i meant|i mean|i said|i say|instead of|mera matlab|maine kaha)\b")


def looks_like_correction(command: str) -> bool:
    """'no, I meant...', 'not only open the URL', 'maine kaha tha...': a change to the previous request, not a new one."""
    return bool(CORRECTION.search(command or ""))
