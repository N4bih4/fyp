"""Platform helpers: open files/folders/URLs with the OS default handler."""
from __future__ import annotations

import os
import platform
import subprocess


def open_path_with_os(path: str) -> None:
    """Open a path with the operating system's default application.

    Raises OSError/RuntimeError when the platform cannot handle the request.
    Tests monkeypatch this function to avoid launching real GUI programs.
    """
    system = platform.system()
    if system == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def launch_program(executable: str, args: list[str] | None = None) -> subprocess.Popen:
    """Launch a program without waiting for it. Tests monkeypatch this too."""
    options = {}
    if platform.system() == "Windows" and executable.replace("\\", "/").rsplit("/", 1)[-1].casefold() in {"powershell.exe", "pwsh.exe"}:
        # The backend has no console. A requested shell app must get its own
        # visible interactive console, instead of inheriting hidden handles.
        options["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    return subprocess.Popen([executable, *(args or [])], **options)
