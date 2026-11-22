"""Spoken File Explorer navigation INSIDE an open Explorer lane: "C drive kholo", "Users", "Documents kholo", "peeche jao", "ek level upar".

Only used while the current lane is an Explorer lane. The words are resolved against the folder the lane's window shows:
a drive letter, a known folder (Desktop, Downloads ...), a sub-folder of the shown folder (fuzzy, so Whisper's spelling does not matter), or "back / up"
(the parent folder). It returns a result for the caller to act on:
    ("go", path)               navigate the lane's window to this folder
    ("ask", [paths])           several sub-folders fit equally: ask which
    None                       not a navigation sentence for this folder: the normal parsers take it
Nothing here touches the PC except listing the shown folder.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

NOT_NAVIGATION = re.compile(
    r"\b(?:create|make|new|delete|remove|rename|copy|move|paste|search|find|write|read|play|pause|mute|volume|brightness|close|shutdown|restart|banao|bana|naya|"
    r"hatao|mita|nakal|dhundo|dhoondo|likho|parho|chalao|band|screenshot|email|mail|send|bhejo|install|uninstall)\b", re.I)
VERBS = r"(?:open|go\s+(?:in|into|to|inside)|enter|show|kholo|khol\s+do|kholna|dikhao|dikha\s+do|andar\s+jao|jao|chalo)"
TAIL = r"(?:\s+(?:ka|ki|ke|wala|wali|folder|directory|drive|kholo|khol\s+do|open|mein\s+jao|me\s+jao|andar\s+jao|dikhao|karo|kar\s+do|pe\s+jao|par\s+jao|jao|please|na))*"
UP = re.compile(r"^(?:please\s+)?(?:go\s+back|back|go\s+up|up|up\s+one\s+level|one\s+level\s+up|parent(?:\s+folder)?|go\s+to\s+the\s+parent(?:\s+folder)?|"
                r"peeche\s+jao|peechay\s+jao|piche\s+jao|wapas\s+jao|upar\s+jao|ek\s+level\s+upar|ek\s+folder\s+upar|pichhe\s+jao|"
                r"पीछे\s+जाओ|ऊपर\s+जाओ|वापस\s+जाओ)$", re.I)
DRIVE = re.compile(rf"^(?:please\s+)?(?:{VERBS}\s+)?(?:(?:the\s+)?([a-z])\s*(?:drive|ڈرائیو|ड्राइव|:)|drive\s+([a-z])(?:\s+(?:kholo|open))?){TAIL}$", re.I)
_DRIVE_ANY = re.compile(r"(?<![a-z])(?:([a-z])\s*(?:drive|ڈرائیو|ड्राइव)|drive\s+([a-z]))(?![a-z])", re.I)
_NOT_THIS_PC = re.compile(r"(?:google|gdrive|one|my|shared)\s*drive|(?:usb|pen|flash|hard|disk|dvd|cd)\s*drive", re.I)


def drive_letter(text: str) -> str | None:
    """The drive letter a short, spoken sentence is about, however it is put: "C drive ko open karo", "Explorer mein C drive kholo", "go to the D drive please".
    None for a long sentence, an action that is not navigation ("create a file in C drive") or Google Drive."""
    low = " ".join(str(text or "").casefold().strip(" .!?,;:।۔").split())
    if not low or len(low.split()) > 9 or NOT_NAVIGATION.search(low) or _NOT_THIS_PC.search(low):
        return None
    m = _DRIVE_ANY.search(low)
    return (m.group(1) or m.group(2)).upper() if m else None


DEVANAGARI_DRIVE = re.compile(r"^(?:(?:सी|डी|ई|एफ़?|जी)\s*ड्राइव)(?:\s*(?:खोलो|खोल\s+दो|ओपन\s*करो))?$")
KNOWN = {"desktop": "Desktop", "downloads": "Downloads", "download": "Downloads", "documents": "Documents", "document": "Documents", "pictures": "Pictures",
         "music": "Music", "videos": "Videos", "home": "", "user folder": "", "my files": "Documents"}
DEVA_LETTER = {"सी": "C", "डी": "D", "ई": "E", "एफ": "F", "एफ़": "F", "जी": "G"}


def _clean(text: str) -> str:
    t = " ".join(str(text or "").strip().strip(".!?,;:।۔").split())
    return t


def _name_of(text: str) -> str | None:
    """The folder name the sentence is about ("open Users folder" -> "users"), or None for a sentence that is not one."""
    low = _clean(text).casefold()
    if not low or len(low.split()) > 6 or NOT_NAVIGATION.search(low):
        return None
    m = re.fullmatch(rf"(?:please\s+)?(?:{VERBS}\s+)?(?:the\s+)?(.+?){TAIL}", low)
    return m.group(1).strip() if m else None


def _children(folder: str) -> list[str]:
    try:
        return sorted(e.name for e in os.scandir(folder) if e.is_dir(follow_symlinks=False))
    except OSError:
        return []


def explorer_navigation(text: str, folder: str | None):
    """See the module docstring. `folder` is the folder the lane's window shows (None = nothing known: only drives and known folders)."""
    low = _clean(text).casefold()
    if not low:
        return None
    if UP.match(low):
        if folder:
            parent = str(Path(folder).parent)
            return ("go", parent) if parent and os.path.normcase(parent) != os.path.normcase(folder.rstrip("\\/") or folder) else None
        return None
    letter = drive_letter(low)
    if letter:
        root = f"{letter}:\\"
        return ("go", root) if os.path.isdir(root) else None
    deva = DEVANAGARI_DRIVE.match(low)
    if deva:
        root = f"{DEVA_LETTER.get(low.split()[0], 'C')}:\\"
        return ("go", root) if os.path.isdir(root) else None
    name = _name_of(low)
    if not name:
        return None
    if folder:                                                       # a sub-folder of the shown folder with exactly this name wins over a known folder
        exact = [child for child in _children(folder) if child.casefold() == name]
        if exact:
            return ("go", str(Path(folder) / exact[0]))
    if name in KNOWN:
        target = Path.home() / KNOWN[name]
        return ("go", str(target)) if target.is_dir() else None
    if folder and len(name) >= 3:
        from rapidfuzz import fuzz
        scored = sorted(((fuzz.ratio(name, child.casefold()), child) for child in _children(folder)), reverse=True)
        scored = [s for s in scored if s[0] >= 80 or (len(name) >= 4 and s[1].casefold().startswith(name))]
        if scored:
            top = scored[0][0]
            close = [child for score, child in scored if score >= top - 4]
            if len(close) == 1:
                return ("go", str(Path(folder) / close[0]))
            return ("ask", [str(Path(folder) / child) for child in sorted(close, key=str.casefold)[:3]])      # a stable order: "the second one" means the second name spoken
    return None


def pick_from(paths: list[str], reply: str) -> str | None:
    """The answer to "Which one: A or B?": a number, an ordinal or a (part of a) name."""
    words = _clean(reply).casefold().split()
    ordinal = {"first": 0, "1": 0, "pehla": 0, "pehli": 0, "one": 0, "second": 1, "2": 1, "doosra": 1, "dusra": 1, "doosri": 1, "two": 1,
               "third": 2, "3": 2, "teesra": 2, "teesri": 2, "three": 2}
    for w in words:
        if w in ordinal and ordinal[w] < len(paths):
            return paths[ordinal[w]]
    text = " ".join(words)
    hits = [p for p in paths if Path(p).name.casefold() in text or (text and text in Path(p).name.casefold())]
    return hits[0] if len(hits) == 1 else None
