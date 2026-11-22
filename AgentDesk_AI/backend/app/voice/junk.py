"""Decide whether a transcript is real speech or noise Whisper (or the browser's recogniser) made words from.

An always-listening orb hears fans, TV, keyboards and breathing; Whisper then "hears" things like "Ffff!", "Danke.", "Thank you for watching" or
"yuk yuk yuk yuk". Those must never become commands. Returns the reason (a short string) when the transcript is junk, else None. The decision uses the
text, and, when Whisper's own numbers are given, how sure Whisper was that anybody spoke at all.
"""
from __future__ import annotations

import re

HALLUCINATIONS = {
    "thanks for watching", "thank you for watching", "thanks for watching!", "please subscribe", "subscribe to my channel", "like and subscribe",
    "subtitles by the amara.org community", "amara.org", "danke", "danke.", "vielen dank", "merci", "obrigado", "gracias", "ご視聴ありがとうございました",
    "www.mooji.org", "bye", "bye.", "you", "mm", "hmm", "uh", "um", "ah", "oh",
}
# Sounds and courtesies that are never a command (an "ok / yes / haan" IS one: it answers a question, so those are not listed).
INTERJECTIONS = {"aduh", "aduhh", "aduly", "ouch", "oops", "ugh", "huh", "tsk", "haha", "hehe", "wow", "yay", "phew", "hmm", "thank you", "thanks", "thank you very much",
                 "shukriya", "shukria", "thanks a lot"}
_ADDRESS = re.compile(r"https?://|\bwww\.|\b[\w-]+\.(?:com|org|net|au|uk|pk|io|co|info)\b|=\"")
_WEB_VERB = re.compile(r"\b(?:open|go\s+to|visit|browse|search|play|summari[sz]e|read|translate|download|save|share|check|watch|send|copy|bookmark|kholo|khol|chalao|chalo|dhundo|dhoondo|dikhao|parho|dekho|bhejo|save\s+karo|e-?mail|mail|draft|compose|write|likho|message)\b|کھولو|खोलो", re.I)
_FOREIGN_SCRIPT = re.compile("[Ѐ-ӿͰ-Ͽ฀-๿぀-ヿ㐀-鿿가-힯]")      # Cyrillic, Greek, Thai, kana, CJK, Hangul
# Languages this assistant is spoken in. Whisper names the language it detected; anything else (Italian, Indonesian, Somali ... on room noise) is not a command.
SPOKEN_LANGUAGES = {"english", "en", "urdu", "ur", "hindi", "hi", "punjabi", "pa", "arabic", "ar", "persian", "fa", "sindhi", "sd", "pashto", "ps"}
_LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)


def junk_reason(text: str, *, language: str | None = None, no_speech_prob: float | None = None, avg_logprob: float | None = None, compression_ratio: float | None = None) -> str | None:
    clean = " ".join((text or "").split())
    if not clean:
        return "empty"
    if language and str(language).strip().casefold() not in SPOKEN_LANGUAGES:
        return f"Whisper heard '{language}', a language nobody speaks to this assistant (room noise)"
    letters = _LETTERS.findall(clean)
    if len(letters) < 2:
        return "no words"                                   # ".", "Ffff!" has letters but see below, "?" , "..."
    low = clean.casefold().strip(" .!?,…")
    if low in HALLUCINATIONS or any(h in low for h in ("amara.org", "thanks for watching", "thank you for watching", "subscribe to")):
        return "known Whisper phantom phrase"
    if len(_FOREIGN_SCRIPT.findall(clean)) * 2 > len(letters):
        return "a script this assistant is not spoken in (Whisper guessed the wrong language from noise)"
    if low in INTERJECTIONS or re.sub(r"[^a-z ]", "", low).strip() in INTERJECTIONS:
        return "a sound or a courtesy, not a command"
    if _ADDRESS.search(low) and not _WEB_VERB.search(low):
        return "a web address with no command (subtitle credit or noise)"
    words = re.findall(r"[^\W\d_]+", low)
    if words and len(set(words)) == 1 and len(words) >= 3:
        return "the same word repeated"                    # "yuk yuk yuk yuk"
    if len(words) >= 6 and len(set(words)) / len(words) < 0.34:
        return "mostly repeated words"
    if len(set(low.replace(" ", ""))) <= 2 and len(low) >= 4:
        return "one or two letters repeated"               # "ffff", "ahhhh"
    if compression_ratio is not None and compression_ratio > 2.4:
        return "repetitive audio (compression ratio)"
    if no_speech_prob is not None and avg_logprob is not None and no_speech_prob > 0.6 and avg_logprob < -0.8:
        return "Whisper says nobody spoke"
    if avg_logprob is not None and avg_logprob < -1.4:
        return "Whisper was not sure of the words"
    return None
