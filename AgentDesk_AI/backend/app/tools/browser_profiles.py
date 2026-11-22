"""open_browser_profile: open Chrome or Edge in ONE named profile ("open Chrome with the Zain profile", "work wali profile kholo").

Chrome and Edge keep their profiles in "<User Data>\\Local State" (profile.info_cache: folder -> display name, Google account name / address).
A spoken name is matched against those names; when two profiles fit about equally the tool asks which one (needs_confirmation, like open_application)
instead of guessing, and an optional website opens inside that profile. Only the browser's own `--profile-directory` switch is used.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..verification import verdict, window_check
from . import platform as _platform
from .base import BaseTool, RiskLevel, ToolContext, ToolResult, Verification

BROWSERS = {
    "chrome": {"data": ("Google", "Chrome", "User Data"), "exe": ("Google", "Chrome", "Application", "chrome.exe"), "process": "chrome.exe", "title": "chrome"},
    "edge": {"data": ("Microsoft", "Edge", "User Data"), "exe": ("Microsoft", "Edge", "Application", "msedge.exe"), "process": "msedge.exe", "title": "edge"},
}


def user_data_dir(browser: str) -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")), *BROWSERS[browser]["data"])


def list_profiles(browser: str, data_dir: Path | None = None) -> list[dict]:
    """[{'dir': 'Profile 2', 'name': 'Zain', 'account': 'zain', 'email_name': ...}] from Local State (no e-mail address is ever returned or logged)."""
    state = (data_dir or user_data_dir(browser)) / "Local State"
    try:
        cache = json.loads(state.read_text(encoding="utf-8")).get("profile", {}).get("info_cache", {})
    except (OSError, ValueError):
        return []
    out = []
    for folder, info in cache.items():
        if not isinstance(info, dict):
            continue
        email = str(info.get("user_name") or "")
        out.append({"dir": folder, "name": str(info.get("name") or folder), "account": str(info.get("gaia_name") or ""), "email_name": email.split("@")[0]})
    return sorted(out, key=lambda p: p["dir"])


def _norm(text: str) -> str:
    return "".join(ch for ch in str(text).casefold() if ch.isalnum())


def match_profile(profiles: list[dict], spoken: str) -> tuple[dict | None, list[dict]]:
    """(the profile, []) when one fits clearly; (None, candidates) when several fit; (None, []) when none does."""
    from rapidfuzz import fuzz

    wanted = _norm(spoken.replace("profile", "").replace("wali", "").replace("wala", ""))
    if not wanted:
        return None, profiles[:3]
    if wanted.isdigit():                                   # "profile 7" / "profile number 7": the folder name
        folder = [p for p in profiles if _norm(p["dir"]) == f"profile{wanted}"]
        if folder:
            return folder[0], []
    scored = []
    for p in profiles:
        names = [_norm(p["name"]), _norm(p["account"]), _norm(p["email_name"]), _norm(p["dir"])]
        best = max((100 if wanted == n else fuzz.WRatio(wanted, n) for n in names if n), default=0)
        scored.append((best, p))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < 72:
        return None, []
    top = scored[0][0]
    close = [p for score, p in scored if score >= top - 8]
    return (close[0], []) if len(close) == 1 else (None, close[:3])


def find_executable(browser: str) -> Path | None:
    spec = BROWSERS[browser]
    found = shutil.which("chrome" if browser == "chrome" else "msedge")
    if found:
        return Path(found)
    for root in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(root)
        if base and (Path(base, *spec["exe"])).is_file():
            return Path(base, *spec["exe"])
    return None


class OpenBrowserProfileArgs(BaseModel):
    profile: str = Field(default="", description="The profile's name as spoken, e.g. 'Zain' or 'Work'. Empty = list the profiles.")
    browser: Literal["chrome", "edge"] = "chrome"
    url: str | None = Field(default=None, description="Optional http(s) website to open in that profile.")
    picker: bool = Field(default=False, description="True to show the browser's own profile screen ('Who's using Chrome?') so the user picks the profile there: for "
                         "'open another profile', 'show me the profiles', 'switch profile' when no profile is named.")


class OpenBrowserProfileTool(BaseTool):
    name = "open_browser_profile"
    description = ("Open Chrome (default) or Edge in one of its profiles by the profile's name. Use when the user names a browser profile "
                   "('open the Work profile', 'Zain wali profile kholo'). Optional url opens a website in that profile.")
    risk_level = RiskLevel.LOW
    args_schema = OpenBrowserProfileArgs

    def execute(self, args: BaseModel) -> ToolResult:
        a = OpenBrowserProfileArgs.model_validate(args.model_dump())
        if platform.system() != "Windows":
            return ToolResult(success=False, error="Browser profiles are supported on Windows only.")
        if a.url and not a.url.strip().startswith(("http://", "https://")):
            return ToolResult(success=False, error="Only http:// and https:// websites can be opened.")
        profiles = list_profiles(a.browser)
        if not profiles:
            return ToolResult(success=False, error=f"No {a.browser} profiles were found on this PC.")
        profile, candidates = match_profile(profiles, a.profile) if a.profile and not a.picker else (None, [])
        if a.picker or (profile is None and not candidates):
            return self._show_picker(a, profiles, missing=bool(a.profile and not a.picker))
        if profile is None:
            shown = candidates or profiles[:3]
            taken = [c["name"] for c in shown]
            names = [c["name"] if taken.count(c["name"]) == 1 else f"{c['name']} ({c['dir']})" for c in shown]   # two profiles can share a name
            question = f"Which {a.browser} profile: {', '.join(names)}?" if candidates or not a.profile else f"I could not find a profile called {a.profile}. Which one: {', '.join(names)}?"
            return ToolResult(success=False, output={"candidates": names, "needs_confirmation": True, "question": question}, error=question)
        exe = find_executable(a.browser)
        if exe is None:
            return ToolResult(success=False, error=f"{a.browser} was not found on this PC.")
        _platform.launch_program(str(exe), [f"--profile-directory={profile['dir']}", *([a.url.strip()] if a.url else [])])
        return ToolResult(success=True, output={"browser": a.browser, "profile": profile["name"], "profile_dir": profile["dir"], "launched": True,
                                                "spoken": f"Opened {a.browser} with the {profile['name']} profile."})

    def _show_picker(self, a: "OpenBrowserProfileArgs", profiles: list[dict], missing: bool) -> ToolResult:
        """The browser's own "Who's using Chrome?" screen: the user sees every profile and says which one. Also the answer when a spoken name matches none."""
        exe = find_executable(a.browser)
        if exe is None:
            return ToolResult(success=False, error=f"{a.browser} was not found on this PC.")
        scheme = "chrome" if a.browser == "chrome" else "edge"
        _platform.launch_program(str(exe), [f"{scheme}://profile-picker/"])
        names = ", ".join(p["name"] for p in profiles[:8])
        spoken = (f"I could not find a profile called {a.profile}, so I opened the profile screen. " if missing else "Here is the profile screen. ") + "Say which profile to open."
        return ToolResult(success=True, output={"browser": a.browser, "picker": True, "launched": True, "profiles": [p["name"] for p in profiles], "spoken": f"{spoken} ({names})"})

    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        if not result.success:
            return Verification(passed=False, checks=[], details=result.error or "tool reported failure")
        spec = BROWSERS[str((result.output or {}).get("browser") or "chrome")]
        seen, evidence = window_check(title_contains=[spec["title"]], processes={spec["process"]}, match="any", focus=True)
        return verdict([(f"a {spec['title']} window is open", seen)], evidence, details=None if seen else "The browser did not show a window in time.")


def profile_tools(ctx: ToolContext | None = None) -> list[BaseTool]:
    return [OpenBrowserProfileTool(ctx or ToolContext.from_settings())]
