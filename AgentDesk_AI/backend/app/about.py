"""What the assistant knows about itself and its project: who made it, who supervised it. Answered here, without the cloud,
so it never says "I don't know"."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

PRODUCT = "AgentDesk AI"
DEVELOPER = "Nabiha Zainab"
UNIVERSITY = "Riphah International University"
PROGRAM = "Software Engineering"
SEMESTER = "7th semester"
SUPERVISOR = "Ms. Uzma Kiran"
SUPERVISOR_ROLE = "Lecturer"
COSUPERVISOR = "Sir Adnan Ahmed Pracha"

DEVELOPER_BIO = (f"{DEVELOPER} is a {SEMESTER} {PROGRAM} student at {UNIVERSITY}. She designed and built {PRODUCT} as her final year project, "
                 f"supervised by {SUPERVISOR} ({SUPERVISOR_ROLE}), with {COSUPERVISOR} as co-supervisor.")

# Told to the cloud AI as well, so a differently worded question gets the same answer.
FACT = (f"About yourself: you are part of {PRODUCT}, a voice-controlled Windows desktop assistant. {DEVELOPER} is its developer: "
        f"she designed and built all of it as her final year project. She is a {SEMESTER} {PROGRAM} student at {UNIVERSITY}. "
        f"Her supervisor is {SUPERVISOR} ({SUPERVISOR_ROLE}) and her co-supervisor is {COSUPERVISOR}. "
        f"If anyone asks who made, created, developed or designed you or {PRODUCT}, or who supervised it, answer with these facts.")

_TARGET = "agentdesk"
_SKELETON = re.sub(r"[aeiou]", "", _TARGET)
_SELF = re.compile(r"\b(?:you|your|yourself|this (?:project|app|application|assistant|software|system|program|tool)|tum|tumhe|tumhein|tumhara|tumhari|"
                   r"aap|aapko|aapka|aapki|tumko|yeh|ye)\b|तुम|आप|तुम्हें|आपको|आपका|तुम्हारा|یہ|آپ|تم", re.I)
_MAKER = re.compile(r"\b(?:develop\w*|creat\w*|made|make|maker|built|build\w*|design\w*|programm\w*|author|owner|founder|behind|invent\w*|"
                    r"banaya|banai|bnaya|banane|bnane|banaye|likha|kisne|developer)\b|बनाया|बनाई|बनाने|डेवलप|डिज़ाइन|डिजाइन|किसने|بنایا|بنائی|بنانے|کس نے|ڈویلپر", re.I)
_WHO = re.compile(r"\b(?:who|who's|whos|wu|hu|hoo|whom|whose|kaun|kon|kaunsa|kisne|kis ne|kiska|kiski|name|naam)\b|कौन|किसने|किसका|किसकी|नाम|کون|کس نے|کس کا|کس کی|نام", re.I)
_ASK = re.compile(r"\b(?:who|who's|whos|wu|hu|hoo|what|which|tell|about|info|details?|kaun|kon|kya|kaunsi|konsi|batao|bataiye|btao|kahan|kis)\b|कौन|क्या|कौनसी|बताओ|कहाँ|کون|کیا|بتاؤ|کہاں", re.I)
_NABIHA = re.compile(r"\bnab+[ie]+h?[ae]?h?\b|\bnabi?ha\b|नबीहा|नबीहः|نبیحہ|نبیہا", re.I)
_UZMA = re.compile(r"\b(?:uzma|usma|uzmaa|osma|uzmah)\b|उस्मा|उज्मा|عظمیٰ|اظمہ", re.I)
_ADNAN = re.compile(r"\b(?:adnan|adnaan|pracha|parcha)\b|अदनान|प्राचा|عدنان|پراچہ", re.I)
_SUPERVISION = re.compile(r"\b(?:super\s?visor|super\s?vise\w*|supervision|guide|mentor|advisor|adviser|co[- ]?super\w*)\b|सुपरवाइजर|सुपरवाईजर|سپروائزر|گائیڈ", re.I)
_COSUPERVISOR = re.compile(r"\bco[- ]?super\w*|\bco\s+super\w*|को-?\s?सुपर|کو[- ]?سپر", re.I)
_PROJECT = re.compile(r"\b(?:project|fyp|thesis|report|final year)\b|प्रोजेक्ट|پروجیکٹ", re.I)
_BIO_TOPIC = re.compile(r"\b(?:university|semester|study|studies|studying|degree|student|program|course|campus|college|education|qualification|kahan|konsi|"
                        r"pad(?:h|hti|hta)|parh)\b|यूनिवर्सिटी|सेमेस्टर|पढ़|यونیورسٹی|سمسٹر|پڑھ", re.I)
_COMMAND_START = re.compile(r"^(?:open|close|create|make|delete|remove|move|copy|rename|named|name|zip|unzip|send|write|edit|play|show|email|mail|message|call|whatsapp|text|draft|compose|kholo|banao|hatao|bhejo)\b", re.I)
_ROMAN_OR_NATIVE = re.compile(r"[^\x00-\x7f]|\b(?:kaun|kon|kisne|banaya|banai|hai|hain|tum|aap|tumhe|aapko|ka|ki|ke|kya|batao|bataiye|btao|kahan)\b", re.I)


def _clean(text: object) -> str:
    """One line, NFC, and no nukta (so "सुपरवाइज़र" and "सुपरवाइजर" are the same word)."""
    return " ".join(unicodedata.normalize("NFC", str(text or "")).replace("\u093c", "").split())


_PRODUCT_NATIVE = re.compile(r"एजें?ट\s*डेस्क|एजेन्ट\s*डेस्क|ایجنٹ\s*ڈیسک")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.casefold())


def names_the_product(text: str) -> bool:
    """AgentDesk however it was heard: Agent Desk, AdenDesk, Adenedask, Agentdesk AI, Agent X."""
    if _PRODUCT_NATIVE.search(_clean(text)):
        return True
    tokens = _tokens(text)
    for size in (1, 2, 3):
        for i in range(len(tokens) - size + 1):
            joined = "".join(tokens[i:i + size])
            if joined in {"agentx", "agentxai"}:
                return True
            if len(joined) < 6:
                continue
            if SequenceMatcher(None, joined, _TARGET).ratio() >= 0.8:
                return True
            skeleton = re.sub(r"[aeiou]", "", joined)             # "adenedask" / "aidendesk": the consonants d-n-d-s-k are the same as g-n-t-d-s-k
            if joined[0] in "ae" and len(skeleton) >= 5 and skeleton.endswith("sk") and _distance(skeleton, _SKELETON) <= 2:
                return True
    return False


def _distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            row.append(min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = row
    return previous[-1]


def _reply(english: str, roman: str, text: str) -> str:
    return roman if _ROMAN_OR_NATIVE.search(text) else english


def _about_me(text: str) -> bool:
    return names_the_product(text) or bool(_SELF.search(text))


def developer_answer(command: str) -> str | None:
    """The answer when `command` asks who made / developed / designed this assistant, or says who did. None for anything else."""
    text = _clean(command)
    if not text or len(text) > 240 or not _MAKER.search(text):
        return None
    if not _about_me(text):
        return None
    if _NABIHA.search(text) and not re.search(r"\b(?:not|nahi|nahin|nhi|isn'?t|never)\b|नहीं|نہیں", text, re.I):
        return _reply(f"Yes, {DEVELOPER} is the developer of {PRODUCT}. She designed and built it.",
                      f"Ji haan, {PRODUCT} ki developer {DEVELOPER} hain. Unhon ne ise design aur develop kiya hai.", text)
    if _WHO.search(text) or text.rstrip().endswith("?"):
        return _reply(f"{PRODUCT} was designed and developed by {DEVELOPER}.",
                      f"{PRODUCT} ko {DEVELOPER} ne design aur develop kiya hai.", text)
    return None


def supervisor_answer(command: str) -> str | None:
    """Who supervised the project, who is the co-supervisor, and who Ms. Uzma Kiran / Sir Adnan Ahmed Pracha are."""
    text = _clean(command)
    if not text or len(text) > 240 or _COMMAND_START.match(text):
        return None
    asking = bool(_ASK.search(text)) or text.rstrip().endswith("?")
    if not asking:
        return None
    if _SUPERVISION.search(text) and (_about_me(text) or _PROJECT.search(text) or _NABIHA.search(text)):
        if _COSUPERVISOR.search(text):
            return _reply(f"The co-supervisor of {PRODUCT} is {COSUPERVISOR}.", f"{PRODUCT} ke co-supervisor {COSUPERVISOR} hain.", text)
        return _reply(f"The supervisor of {PRODUCT} is {SUPERVISOR} ({SUPERVISOR_ROLE}), and the co-supervisor is {COSUPERVISOR}.",
                      f"{PRODUCT} ki supervisor {SUPERVISOR} ({SUPERVISOR_ROLE}) hain, aur co-supervisor {COSUPERVISOR} hain.", text)
    if _UZMA.search(text) and re.search(r"\b(?:who|kaun|kon|about|tell|batao)\b|कौन|बताओ|کون", text, re.I):
        return _reply(f"{SUPERVISOR} is a {SUPERVISOR_ROLE} at {UNIVERSITY} and the supervisor of {PRODUCT}.",
                      f"{SUPERVISOR} {UNIVERSITY} mein {SUPERVISOR_ROLE} hain aur {PRODUCT} ki supervisor hain.", text)
    if _ADNAN.search(text) and re.search(r"\b(?:who|kaun|kon|about|tell|batao)\b|कौन|बताओ|کون", text, re.I):
        return _reply(f"{COSUPERVISOR} is the co-supervisor of {PRODUCT}.", f"{COSUPERVISOR} {PRODUCT} ke co-supervisor hain.", text)
    return None


def developer_info_answer(command: str) -> str | None:
    """Who the developer is: "who is Nabiha Zainab", "tell me about the developer", "which university is the developer from"."""
    text = _clean(command)
    if not text or len(text) > 240 or _COMMAND_START.match(text):
        return None
    asking = bool(_ASK.search(text)) or text.rstrip().endswith("?")
    if not asking:
        return None
    if _NABIHA.search(text) and not _MAKER.search(text):
        return _reply(DEVELOPER_BIO, f"{DEVELOPER} {UNIVERSITY} mein {SEMESTER} ki {PROGRAM} ki student hain. Unhon ne {PRODUCT} apne final year project ke tor par banaya, "
                                     f"{SUPERVISOR} ({SUPERVISOR_ROLE}) ki nigrani mein, aur {COSUPERVISOR} co-supervisor hain.", text)
    other = re.search(r"\b(?:developer|creator|maker) of (?:the |a |an )?(.+?)(?: from| in| at|\?|$)", text, re.I)
    if other and not _about_me(other.group(1)) and not _PROJECT.search(other.group(1)):
        return None                                           # "the developer of Windows": somebody else's developer
    if re.search(r"\b(?:developer|creator|maker)\b|डेवलपर|ڈویلپر", text, re.I) and _BIO_TOPIC.search(text) and (_about_me(text) or not other):
        return _reply(DEVELOPER_BIO, f"{DEVELOPER} {UNIVERSITY} mein {SEMESTER} ki {PROGRAM} ki student hain.", text)
    if re.search(r"\b(?:about|tell)\b.*\b(?:developer|creator)\b|\bdeveloper\b.*\b(?:details?|info)\b", text, re.I) and _about_me(text):
        return _reply(DEVELOPER_BIO, f"{DEVELOPER} {UNIVERSITY} mein {SEMESTER} ki {PROGRAM} ki student hain.", text)
    return None


def own_answer(command: str) -> str | None:
    """The first of the answers above that fits; None when the question is about something else."""
    return developer_answer(command) or supervisor_answer(command) or developer_info_answer(command)
