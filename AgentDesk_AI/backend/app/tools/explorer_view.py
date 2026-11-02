"""File Explorer, the window itself: sort, view mode, show / hide hidden files, properties, search.

Creating, renaming, moving, copying, deleting and opening files and folders are the file tools (they ask first, keep an undo copy and verify on disk).
This tool only changes HOW an open Explorer window shows things, through Windows' own Shell object (no clicking and no guessing):
 - sort / view: set on the front Explorer window's folder view, then READ BACK from the same view;
 - hidden files: the same switch as Explorer's "View > Show > Hidden items" (a user setting: medium risk), read back from the registry and the open windows refreshed;
 - properties: Windows' own Properties dialog for a path; checked by looking for the dialog window;
 - search: Explorer's own search results window for words, in a folder.
Everything the OS does is behind `ExplorerBackend`, so the tests run on a fake.
"""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from ..security.paths import resolve_within_allowed
from .base import BaseTool, RiskLevel, ToolContext, ToolResult, Verification

SORT_KEYS = {"name": "System.ItemNameDisplay", "date": "System.DateModified", "size": "System.Size", "type": "System.ItemTypeText"}
VIEW_MODES = {"icons": 1, "small_icons": 2, "list": 3, "details": 4, "large_icons": 5, "tiles": 6}
ADVANCED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"


class ExplorerBackend(Protocol):
    def front(self) -> dict | None: ...
    def set_sort(self, column: str) -> None: ...
    def sort(self) -> str: ...
    def set_view(self, mode: int) -> None: ...
    def view(self) -> int: ...
    def hidden(self) -> bool: ...
    def set_hidden(self, show: bool) -> None: ...
    def properties(self, path: str) -> None: ...
    def window_titles(self) -> list[str]: ...
    def search(self, folder: str, query: str) -> None: ...


class WindowsExplorer:
    """Shell.Application through comtypes (installed with pywinauto)."""

    @staticmethod
    def _windows():
        import comtypes.client
        shell = comtypes.client.CreateObject("Shell.Application")
        found = []
        wins = shell.Windows()
        for i in range(wins.Count):
            try:
                w = wins.Item(i)
                if w is not None and str(w.LocationURL).startswith("file:///"):
                    found.append(w)
            except Exception:  # noqa: BLE001 - Internet Explorer / non-folder windows
                continue
        return found

    def _front_window(self):
        windows = self._windows()
        if not windows:
            return None
        fg = ctypes.windll.user32.GetForegroundWindow()
        return next((w for w in windows if int(w.HWND) == fg), windows[-1])

    def front(self) -> dict | None:
        w = self._front_window()
        if w is None:
            return None
        from urllib.parse import unquote, urlsplit
        path = unquote(urlsplit(str(w.LocationURL)).path.lstrip("/")).replace("/", "\\")
        return {"path": path, "title": str(w.LocationName)}

    def set_sort(self, column: str) -> None:
        self._front_window().Document.SortColumns = column

    def sort(self) -> str:
        return str(self._front_window().Document.SortColumns)

    def set_view(self, mode: int) -> None:
        self._front_window().Document.CurrentViewMode = mode

    def view(self) -> int:
        return int(self._front_window().Document.CurrentViewMode)

    def hidden(self) -> bool:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ADVANCED_KEY) as key:
            return winreg.QueryValueEx(key, "Hidden")[0] == 1

    def set_hidden(self, show: bool) -> None:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ADVANCED_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Hidden", 0, winreg.REG_DWORD, 1 if show else 2)
        for w in self._windows():
            try:
                w.Refresh()
            except Exception:  # noqa: BLE001
                pass

    def properties(self, path: str) -> None:
        from ctypes import wintypes

        class SHELLEXECUTEINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
                        ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                        ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
                        ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]
        info = SHELLEXECUTEINFO()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = 0x0000000C             # SEE_MASK_INVOKEIDLIST: the shell verb "properties" needs it
        info.lpVerb, info.lpFile, info.nShow = "properties", path, 1
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
            raise OSError("Windows would not open the Properties window")

    def window_titles(self) -> list[str]:
        from .uia import get_service
        return [w.title for w in get_service().backend.windows()]

    def search(self, folder: str, query: str) -> None:
        from urllib.parse import quote
        uri = f"search-ms:displayname=Search Results&crumb=location:{quote(folder)}&query={quote(query)}"
        subprocess.Popen(["explorer.exe", uri])


_backend: ExplorerBackend | None = None


def get_explorer() -> ExplorerBackend:
    global _backend
    if _backend is None:
        _backend = WindowsExplorer()
    return _backend


def set_explorer(backend: ExplorerBackend | None) -> None:
    global _backend
    _backend = backend


class ExplorerViewArgs(BaseModel):
    action: Literal["sort", "view", "hidden", "properties", "search"]
    by: Literal["name", "date", "size", "type"] | None = None
    descending: bool = False
    mode: Literal["details", "list", "icons", "small_icons", "large_icons", "tiles"] | None = None
    show: bool | None = None
    path: str | None = Field(default=None, max_length=500)
    query: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _needs(self):
        need = {"sort": self.by is not None, "view": self.mode is not None, "hidden": self.show is not None, "properties": bool(self.path), "search": bool(self.query)}
        if not need[self.action]:
            raise ValueError(f"{self.action} needs " + {"sort": "by (name, date, size, type)", "view": "mode", "hidden": "show (true or false)",
                                                        "properties": "path", "search": "query"}[self.action])
        if self.action == "search" and re.search(r"[\\\"<>|]", self.query or ""):
            raise ValueError("search words may not contain \\ \" < > |")
        return self


class ExplorerViewTool(BaseTool):
    name = "explorer_view"
    description = ("The File Explorer window in front: sort by name / date / size / type, switch the view (details, list, icons, tiles), show or hide hidden "
                   "files, open Properties for a path, search a folder. Creating, moving, renaming, copying and deleting use the file tools.")
    args_schema = ExplorerViewArgs
    risk_level = RiskLevel.LOW
    isolation = "thread"        # Shell COM objects belong to the thread that made them
    timeout_seconds = 30

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)

    def risk_for_args(self, args: BaseModel | None) -> RiskLevel:
        return RiskLevel.MEDIUM if getattr(args, "action", None) == "hidden" else RiskLevel.LOW

    def execute(self, args: BaseModel) -> ToolResult:
        a = ExplorerViewArgs.model_validate(args.model_dump())
        ex = get_explorer()
        try:
            if a.action in ("sort", "view"):
                window = ex.front()
                if window is None:
                    return ToolResult(success=False, error="No File Explorer window is open: open a folder first.")
                if a.action == "sort":
                    column = ("-" if a.descending else "") + SORT_KEYS[a.by]
                    ex.set_sort(f"prop:{column};")
                    time.sleep(0.4)
                    return ToolResult(success=True, output={"action": "sort", "by": a.by, "descending": a.descending, "folder": window["path"], "sort_now": ex.sort(),
                                                            "spoken": f"Sorted by {a.by}{', newest or largest first' if a.descending else ''}."})
                ex.set_view(VIEW_MODES[a.mode])
                time.sleep(0.3)
                return ToolResult(success=True, output={"action": "view", "mode": a.mode, "folder": window["path"], "view_now": ex.view(), "spoken": f"Showing {a.mode.replace('_', ' ')}."})
            if a.action == "hidden":
                before = ex.hidden()
                ex.set_hidden(a.show)
                return ToolResult(success=True, output={"action": "hidden", "show": a.show, "was": before, "spoken": "Hidden files are shown." if a.show else "Hidden files are hidden."})
            if a.action == "properties":
                path = self._existing(a.path)
                ex.properties(path)
                return ToolResult(success=True, output={"action": "properties", "path": path, "name": Path(path).name, "spoken": f"Properties of {Path(path).name}."})
            window = ex.front()
            folder = self._search_folder(a.path, window)
            ex.search(folder, a.query)
            return ToolResult(success=True, output={"action": "search", "query": a.query, "folder": folder, "spoken": f"Searching {Path(folder).name or folder} for {a.query}."})
        except (ValueError, FileNotFoundError, PermissionError) as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"Explorer did not accept that: {type(exc).__name__}: {str(exc)[:120]}")

    def _existing(self, raw: str) -> str:
        path = resolve_within_allowed(raw, self.ctx.allowed_directories) if self.ctx.allowed_directories else Path(os.path.expandvars(raw)).expanduser().resolve()
        if not Path(path).exists():
            raise FileNotFoundError(f"'{raw}' does not exist.")
        return str(path)

    def _search_folder(self, raw: str | None, window: dict | None) -> str:
        if raw:
            return self._existing(raw)
        return (window or {}).get("path") or str(Path.home())

    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        if not result.success:
            return Verification(passed=False, checks=["action done"], details=result.error)
        a = ExplorerViewArgs.model_validate(args.model_dump())
        out, ex = result.output, get_explorer()
        try:
            if a.action == "sort":
                want = ("-" if a.descending else "") + SORT_KEYS[a.by]
                now = ex.sort()
                return Verification(passed=want in now, checks=["the folder view reports the sort"], evidence={"sort": now})
            if a.action == "view":
                return Verification(passed=ex.view() == VIEW_MODES[a.mode], checks=["the folder view reports the mode"], evidence={"view": ex.view()})
            if a.action == "hidden":
                return Verification(passed=ex.hidden() is a.show, checks=["Explorer's hidden-items setting was read again"], evidence={"hidden_shown": ex.hidden()})
            deadline = time.monotonic() + (5 if a.action == "properties" else 8)
            while time.monotonic() < deadline:
                titles = ex.window_titles()
                if a.action == "properties" and any("Properties" in t and Path(out["path"]).stem.casefold() in t.casefold() for t in titles):    # Windows hides extensions: "a Properties"
                    return Verification(passed=True, checks=["the Properties window is open"], evidence={"windows": [t for t in titles if "Properties" in t][:2]})
                if a.action == "search" and any("Search Results" in t for t in titles):
                    return Verification(passed=True, checks=["a Search Results window is open"], evidence={"windows": [t for t in titles if "Search" in t][:2]})
                time.sleep(0.4)
            return Verification(passed=False, checks=["the window appeared"], details="Windows accepted the request but I did not see the window.")
        except Exception as exc:  # noqa: BLE001
            return Verification(passed=False, checks=["read back"], details=f"{type(exc).__name__}: {str(exc)[:120]}")


def explorer_tools(ctx) -> list[BaseTool]:
    return [ExplorerViewTool(ctx)]
