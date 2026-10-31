"""Exact browser tab matching and idempotent YouTube pause/resume."""
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field
from ..browser_bridge import bridge
from ..verification import failed_result, verdict
from .base import BaseTool, RiskLevel, ToolResult, Verification

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


def _clean_tabs(raw) -> list[dict]:
    """The extension is outside this process; accept only well-formed tab records."""
    tabs = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and isinstance(item.get("id"), int) and not isinstance(item.get("id"), bool):
            tabs.append({
                "id": item["id"],
                "title": str(item.get("title") or "")[:300],
                "url": str(item.get("url") or "")[:2000],
                "active": bool(item.get("active")),
                "audible": bool(item.get("audible")),
            })
    return tabs


def public_tab(tab: dict) -> dict:
    """Tab info that may leave the backend (UI, AI prompts): URLs lose query and fragment,
    which often carry session tokens or private search text."""
    parts = urlsplit(tab.get("url", ""))
    shown = f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.scheme and parts.netloc else ""
    return {**tab, "url": shown}


class BrowserControlArgs(BaseModel):
    action: Literal["inspect", "close", "pause", "resume"]
    target: str = Field(default="youtube", max_length=500)
    tab_id: int | None = Field(default=None, ge=0)


class BrowserControlTool(BaseTool):
    name = "control_browser"
    description = "Inspect actual browser tabs, close one exact named site/title/tab ID, or pause/resume an existing YouTube video. Requires Agent X Browser Bridge extension. Multiple matches require clarification. Never substitutes an active unrelated tab."
    args_schema = BrowserControlArgs
    risk_level = RiskLevel.LOW
    isolation = "thread"  # the extension socket lives in the server process

    def execute(self, args):
        a = BrowserControlArgs.model_validate(args.model_dump())
        observed = bridge.request("inspect")
        if not observed.get("success"):
            return ToolResult(success=False, error=observed.get("error", "Browser inspect failed"))
        tabs = _clean_tabs(observed.get("tabs"))
        if a.action == "inspect":
            return ToolResult(success=True, output={"tabs": [public_tab(t) for t in tabs]})
        matches = [t for t in tabs if t["id"] == a.tab_id] if a.tab_id is not None else select_tabs(tabs, a.target)
        if a.action in {"pause", "resume"}:
            matches = select_tabs(matches, "youtube")
            # For media only, an unambiguous audible YouTube tab is a meaningful target.
            audible = [t for t in matches if t.get("audible")]
            if len(matches) > 1 and len(audible) == 1:
                matches = audible
        if len(matches) != 1:
            shown = "; ".join(f"tab {t['id']}: {t.get('title', '')}" for t in matches)
            return ToolResult(success=False, output={"candidates": [public_tab(t) for t in matches], "needs_confirmation": True}, error="Matching tab nahi mila; unrelated tab ko touch nahi kiya." if not matches else "Multiple matching tabs. Exact title ya tab ID batayein: " + shown)
        tab = matches[0]
        result = bridge.request(a.action, tab_id=tab["id"], expected_url=tab.get("url", ""))
        if not result.get("success"):
            return ToolResult(success=False, error=result.get("error", "Browser action failed"))
        verified = result.get("closed") is True if a.action == "close" else result.get("paused") is (a.action == "pause")
        if not verified:
            return ToolResult(success=False, error="Browser ne requested tab/video state verify nahi ki.")
        return ToolResult(success=True, output={"action": a.action, "tab_id": tab["id"], "title": tab.get("title"), **{k: v for k, v in result.items() if k in {"success", "closed", "paused", "error"}}})

    def verify(self, args, result: ToolResult) -> Verification:
        """Evidence comes from the browser extension (a separate process that reads the real tabs)."""
        if not result.success:
            return failed_result(result)
        a = BrowserControlArgs.model_validate(args.model_dump())
        if a.action == "inspect":
            tabs = result.output.get("tabs", [])
            return verdict([("extension returned the tab list", isinstance(tabs, list))], {"tabs": len(tabs)})
        observed = bridge.request("inspect")
        if not observed.get("success"):
            return Verification(passed=False, checks=["could not re-inspect tabs"], details=observed.get("error"))
        ids = {t["id"] for t in _clean_tabs(observed.get("tabs"))}
        tab_id = result.output.get("tab_id")
        evidence = {"tab_id": tab_id, "tabs_now": len(ids), "extension_reply": {k: result.output.get(k) for k in ("closed", "paused")}}
        if a.action == "close":
            return verdict([("extension confirmed close", result.output.get("closed") is True), ("tab is gone", tab_id not in ids)], evidence)
        return verdict([("extension confirmed video state", result.output.get("paused") is (a.action == "pause")),
                        ("tab still open", tab_id in ids)], evidence)


