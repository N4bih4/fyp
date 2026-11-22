"""Split ONE spoken request that holds several independent jobs into one command per job, so Shadow can give each to a different agent.

    "open notepad and open calculator and take a screenshot"  -> three commands
    "notepad aur calculator kholo"                             -> "notepad kholo", "calculator kholo"
    "open youtube and then play a song"                        -> ONE command (a sequence: the second step needs the first)
    "write an email to Ali saying we are free and happy"       -> ONE command (dictation is never split)

Conservative on purpose: a part must look like a command (starts with an English command verb or ends with a Roman Urdu one), otherwise it is glued to
the part before it. Urdu / Hindi script is not split (a single planner call handles it as before).
"""
from __future__ import annotations

import re

MAX_PARTS = 4
NEVER_SPLIT = re.compile(r"\b(?:e-?mail|mail|message|whatsapp|telegram|dictat\w*|saying|say that|remember|remind\w*|likho|likhna|bhejo|bhej|send|note|"
                         r"write|type|search for|search karo.*\bke\b)\b", re.I)
SEQUENCE = re.compile(r"^(?:and\s+)?(?:then|after that|afterwards|next|phir|fir|uske baad|us ke baad|baad mein)\b", re.I)
SEPARATOR = re.compile(r"\s*(?:,|;|\band\b|\baur\b|\bplus\b|\balso\b|\bsaath hi\b|\bnaz\b)\s+", re.I)
START_VERBS = {"open", "close", "launch", "start", "play", "pause", "resume", "stop", "search", "find", "google", "take", "set", "turn", "mute", "unmute", "increase",
               "decrease", "raise", "lower", "show", "lock", "minimize", "minimise", "maximize", "maximise", "switch", "scroll", "skip", "create", "make", "go",
               "volume", "brightness", "screenshot", "increase", "reduce", "enable", "disable", "restart", "check", "tell", "list", "read", "copy", "run"}
END_VERBS = {"kholo", "kholna", "khol", "karo", "kro", "kardo", "chalao", "chala", "band", "dikhao", "dikha", "rok", "roko", "sunao", "lagao", "laga", "lo", "do",
             "barhao", "kam", "banao", "dhundo", "dhoondo", "batao", "padho", "mute", "unmute", "pause", "play", "skip"}
REFERS_BACK = re.compile(r"\b(?:it|that|this|them|those|there|usko|isko|usse|isse|use|ise|woh|wo|wahan|wahin|usme|isme|us mein|is mein)\b", re.I)
SHARED_VERB_STARTS = {"open", "close", "launch", "start", "play"}


def _first(words: list[str]) -> str:
    return words[0].casefold().strip(".,!?") if words else ""


def _last(words: list[str]) -> str:
    return words[-1].casefold().strip(".,!?") if words else ""


def _looks_like_command(segment: str) -> bool:
    words = segment.split()
    return bool(words) and (_first(words) in START_VERBS or _last(words) in END_VERBS)


def split_command(text: str) -> list[str]:
    text = " ".join(text.split())
    if len(text) < 8 or len(text) > 400 or not text.isascii() or NEVER_SPLIT.search(text):
        return [text]
    pieces = [p.strip(" ,;.") for p in SEPARATOR.split(text) if p and p.strip(" ,;.")]
    if len(pieces) < 2:
        return [text]
    parts: list[str] = []
    for piece in pieces:
        words = piece.split()
        if parts and (SEQUENCE.match(piece) or REFERS_BACK.search(piece) or not _looks_like_command(piece) and len(words) > 3):
            parts[-1] = f"{parts[-1]} and {piece}"          # a sequence ("then ..."), a part that points back ("close it") or a sentence that is not a command: stays with the part before it
        else:
            parts.append(piece)
    # "notepad aur calculator kholo": a verb-less short part before a Roman Urdu verb takes that verb; "open notepad and calculator": takes the opening verb
    for i, part in enumerate(parts):
        words = part.split()
        if _looks_like_command(part) or len(words) > 3:
            continue
        later = next((p for p in parts[i + 1:] if _last(p.split()) in END_VERBS), None)
        earlier = next((p for p in reversed(parts[:i]) if _first(p.split()) in SHARED_VERB_STARTS), None)
        if later is not None and _last(later.split()) in END_VERBS and _first(later.split()) not in START_VERBS:
            parts[i] = f"{part} {_last(later.split())}"
        elif earlier is not None:
            parts[i] = f"{_first(earlier.split())} {part}"
        else:
            return [text]                                      # cannot make a command of it: do not guess
    if len(parts) < 2:
        return [text]
    return parts[:MAX_PARTS - 1] + ([" and ".join(parts[MAX_PARTS - 1:])] if len(parts) > MAX_PARTS else [])
