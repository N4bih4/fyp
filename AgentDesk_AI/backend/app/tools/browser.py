"""Exact browser tab matching and idempotent YouTube pause/resume."""
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field
from ..browser_bridge import bridge
from .base import BaseTool, RiskLevel, ToolResult

SITES = {
    "youtube": {"youtube.com"}, "google drive": {"drive.google.com"}, "drive": {"drive.google.com"},
    "gmail": {"mail.google.com"}, "whatsapp": {"web.whatsapp.com"},
    "openai": {"openai.com"}, "chatgpt": {"chatgpt.com"},
}


def select_tabs(tabs, target):
    target = target.strip().casefold()
    if target in SITES:
        domains = SITES[target]
        return [t for t in tabs if any((urlsplit(t.get("url", "")).hostname or "").casefold() == host or (urlsplit(t.get("url", "")).hostname or "").casefold().endswith("." + host) for host in domains)]
    # Exact title or URL only for unfamiliar names; never arbitrary substring closing.
    return [t for t in tabs if target and target in {t.get("title", "").casefold(), t.get("url", "").casefold()}]


class BrowserControlArgs(BaseModel):
    action: Literal["inspect", "close", "pause", "resume"]
    target: str = Field(default="youtube", max_length=500)
    tab_id: int | None = Field(default=None, ge=0)


class BrowserControlTool(BaseTool):
    name = "control_browser"
    description = "Inspect actual browser tabs, close one exact named site/title/tab ID, or pause/resume an existing YouTube video. Requires Agent X Browser Bridge extension. Multiple matches require clarification. Never substitutes an active unrelated tab."
    args_schema = BrowserControlArgs
    risk_level = RiskLevel.LOW

    def execute(self, args):
        a = BrowserControlArgs.model_validate(args.model_dump())
        observed = bridge.request("inspect")
        if not observed.get("success"):
            return ToolResult(success=False, error=observed.get("error", "Browser inspect failed"))
        tabs = observed.get("tabs", [])
        if a.action == "inspect":
            return ToolResult(success=True, output={"tabs": tabs})
        matches = [t for t in tabs if t["id"] == a.tab_id] if a.tab_id is not None else select_tabs(tabs, a.target)
        if a.action in {"pause", "resume"}:
            matches = select_tabs(matches, "youtube")
            # For media only, an unambiguous audible YouTube tab is a meaningful target.
            audible = [t for t in matches if t.get("audible")]
            if len(matches) > 1 and len(audible) == 1:
                matches = audible
        if len(matches) != 1:
            shown = "; ".join(f"tab {t['id']}: {t.get('title', '')}" for t in matches)
            return ToolResult(success=False, output={"candidates": matches, "needs_confirmation": True}, error="Matching tab nahi mila; unrelated tab ko touch nahi kiya." if not matches else "Multiple matching tabs. Exact title ya tab ID batayein: " + shown)
        tab = matches[0]
        result = bridge.request(a.action, tab_id=tab["id"], expected_url=tab.get("url", ""))
        if not result.get("success"):
            return ToolResult(success=False, error=result.get("error", "Browser action failed"))
        verified = result.get("closed") is True if a.action == "close" else result.get("paused") is (a.action == "pause")
        if not verified:
            return ToolResult(success=False, error="Browser ne requested tab/video state verify nahi ki.")
        return ToolResult(success=True, output={"action": a.action, "tab_id": tab["id"], "title": tab.get("title"), **result})
