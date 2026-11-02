"""Which language was this sentence in? Decides the language of the spoken reply, so a locked "Urdu" setting never answers an English sentence in Urdu.

Script first (Arabic script = Urdu, Devanagari = Hindi); for Latin text, Roman-Urdu marker words against plain English. A short or unclear sentence
returns None and the caller keeps the language setting.
"""
from __future__ import annotations

import re

_ROMAN = {
    "kholo", "khol", "karo", "kar", "dena", "dijiye", "kijiye", "chala", "chalao", "chalado", "lagao", "laga", "band", "bhejo", "bhej", "banao", "bana",
    "dikhao", "dikha", "batao", "bata", "sunao", "suna", "mujhe", "mujhay", "mera", "meri", "mere", "apna", "apni", "ko", "ka", "ki", "ke", "pe",
    "mein", "hai", "hain", "hoon", "tha", "nahi", "nahin", "haan", "han", "aur", "ya", "kya", "kaise", "kahan", "kab", "yeh", "ye", "woh", "wo",
    "isay", "isse", "usay", "gana", "gaana", "gane", "awaz", "aawaz", "kam", "zyada", "thora", "thoda", "barhao", "gharao", "dobara", "phir", "abhi", "bas",
    "shukriya", "ruko", "khatam", "agla", "pichla", "agle", "wala", "wali", "naam", "naya", "purana", "maine", "maene", "bol", "bolo", "likho", "padho", "dhoondo",
}
_EN = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is", "are", "can", "you", "please", "play", "open", "close", "i", "my", "me", "it",
       "that", "this", "not", "only", "also", "what", "how", "say", "said", "want", "make", "create", "show", "send", "find", "search", "music", "file", "folder"}
_WORD = re.compile(r"[A-Za-z']+")


def detect(text: str | None) -> str | None:
    """'en' | 'roman' | 'ur' | 'hi', or None when the text is too short or mixed to say."""
    text = text or ""
    arabic = len(re.findall(r"[؀-ۿ]", text))
    deva = len(re.findall(r"[ऀ-ॿ]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if arabic + deva + latin == 0:
        return None
    if arabic >= max(deva, latin):
        return "ur"
    if deva >= latin:
        return "hi"
    words = [w.casefold() for w in _WORD.findall(text)]
    if not words:
        return None
    roman = sum(w in _ROMAN for w in words)
    english = sum(w in _EN for w in words)
    if roman >= 2 and roman >= english:
        return "roman"
    if roman == 1 and english <= 1 and len(words) <= 4:
        return "roman"
    if english >= 1 and roman == 0 and len(words) >= 3:
        return "en"
    if english >= 2 and english > roman:
        return "en"
    if len(words) >= 5 and roman == 0:
        return "en"
    return None


def normalise(language: str | None) -> str:
    code = (language or "en").lower()
    if code in ("roman", "roman_urdu", "ur-latn", "ur_roman"):
        return "roman"
    if code.startswith("ur"):
        return "ur"
    if code.startswith("hi"):
        return "hi"
    return "en"


def reply_language(text: str | None, setting: str | None) -> str:
    """The language to answer in: the sentence's own language when it is clear, otherwise the setting ('auto' or a locked language)."""
    seen = detect(text)
    if seen:
        return seen
    return normalise(setting)
