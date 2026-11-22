"""Which script the assistant WRITES in (and therefore speaks from).

The user reads English and Roman Urdu (Urdu in Latin letters) but not Devanagari, and does not want Urdu script either. A sentence spoken in Hindi or Urdu is
understood as always, but the answer is written in Roman Urdu. Setting `REPLY_SCRIPT=native` brings back "answer in the script the question came in".
"""
from __future__ import annotations


def reply_lang(lang: str) -> str:
    """"hi" and "ur" become "roman_ur" unless the setting says otherwise; every other language name is left alone."""
    if lang in ("hi", "ur"):
        try:
            from ..config import get_settings
            if get_settings().reply_script.strip().lower() == "native":
                return lang
        except Exception:  # noqa: BLE001
            pass
        return "roman_ur"
    return lang
