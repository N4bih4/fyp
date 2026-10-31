"""WhatsApp Desktop: open a chat with the message pre-filled. The user presses Send (rule 8).

Only `whatsapp://send?phone=...&text=...` is used. No key is ever pressed in WhatsApp, so nothing can be
sent automatically. A contact name is resolved only through a number the user saved on the Memory page
("Ahmed: +923001234567"); there is no contact-list access and no guessing.
"""
from __future__ import annotations

import re
import sys
from urllib.parse import quote

from pydantic import BaseModel, Field, model_validator

from ..verification import ProbeUnavailable, current, failed_result, verdict, window_check
from . import platform as _platform
from .base import BaseTool, RiskLevel, ToolResult, Verification

WHATSAPP_PROCESSES = {"whatsapp.exe", "whatsapp.root.exe", "applicationframehost.exe"}
_PHONE = re.compile(r"\+?\d[\d\s().-]{6,20}\d")


class WhatsAppOpenChatArgs(BaseModel):
    phone: str | None = Field(default=None, max_length=24, description="International number, e.g. +923001234567")
    contact: str | None = Field(default=None, max_length=60, description="Name saved with a number on the Memory page")
    text: str = Field(default="", max_length=1000, description="Message to pre-fill; the user presses Send")

    @model_validator(mode="after")
    def one_target(self):
        if bool(self.phone) == bool(self.contact):
            raise ValueError("give either phone or contact")
        return self


def normalize_phone(raw: str) -> str:
    """Digits of an international number. A local number (leading 0) is refused: its country is unknown."""
    cleaned = re.sub(r"[\s().-]", "", raw.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        raise ValueError("Use the international format with the country code, e.g. +923001234567.")
    digits = cleaned[1:]
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise ValueError("That is not a valid international phone number.")
    return digits


def mask(digits: str) -> str:
    return "+" + digits[:2] + "*" * max(0, len(digits) - 6) + digits[-4:]


def contact_number(name: str) -> str | None:
    """Number saved for `name` on the Memory page (e.g. "Ahmed: +923001234567")."""
    from ..database import SessionLocal
    from ..models import MemoryItem

    wanted = name.strip().casefold()
    with SessionLocal() as db:
        for item in db.query(MemoryItem).all():
            text = item.text.casefold()
            if re.search(rf"(?<!\w){re.escape(wanted)}(?!\w)", text):
                match = _PHONE.search(item.text)
                if match:
                    return match.group(0)
    return None


def whatsapp_installed() -> bool:
    """WhatsApp Desktop registers the whatsapp: protocol."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "whatsapp"):
            return True
    except OSError:
        return False


class WhatsAppOpenChatTool(BaseTool):
    name = "whatsapp_open_chat"
    description = ("Open WhatsApp Desktop on a chat with a message typed in, ready for the user to press Send. "
                   "Never sends. Use phone (international format) or a contact saved with a number in Memory.")
    risk_level = RiskLevel.MEDIUM  # the user sees the exact recipient and text before it opens
    args_schema = WhatsAppOpenChatArgs

    def execute(self, args: BaseModel) -> ToolResult:
        a = WhatsAppOpenChatArgs.model_validate(args.model_dump())
        raw = a.phone or contact_number(a.contact or "")
        if not raw:
            return ToolResult(success=False, output={"needs_confirmation": True},
                              error=f"No number saved for {a.contact!r}. Say the number with country code, or save it on "
                                    f"the Memory page as \"{a.contact}: +92...\".")
        try:
            digits = normalize_phone(raw)
        except ValueError as exc:
            return ToolResult(success=False, output={"needs_confirmation": True}, error=str(exc))
        if not whatsapp_installed():
            return ToolResult(success=False, error="WhatsApp Desktop is not installed (no whatsapp: link handler).")
        uri = f"whatsapp://send?phone={digits}&text={quote(a.text, safe='')}"
        try:
            _platform.open_path_with_os(uri)
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not open WhatsApp: {exc}")
        return ToolResult(success=True, output={"to": mask(digits), "contact": a.contact, "text_chars": len(a.text),
                                                "sent": False, "launched": True})

    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        """WhatsApp's window must be open; when its text box is readable, it must hold the draft."""
        if not result.success:
            return failed_result(result)
        a = WhatsAppOpenChatArgs.model_validate(args.model_dump())
        seen, windows = window_check(title_contains=["whatsapp"], processes=WHATSAPP_PROCESSES)
        checks = [("WhatsApp window is open", seen)]
        evidence = {"to": result.output.get("to"), "sent": False, **windows}
        if seen and a.text:
            pid = (windows.get("windows") or [{}])[0].get("pid")
            try:
                texts = current().dialog_texts(pid) if pid else []
            except ProbeUnavailable:
                texts = []
            if texts:
                prefix = a.text[:30].casefold()
                draft_visible = any(prefix in t.casefold() for t in texts)
                checks.append(("draft text is in the chat box", draft_visible))
            evidence["draft_readable"] = bool(texts)
        return verdict(checks, evidence, details="Not sent: the user presses Send in WhatsApp.")


def messaging_tools(ctx=None) -> list[BaseTool]:
    return [WhatsAppOpenChatTool(ctx)]
