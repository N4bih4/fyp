"""Where bundled resources and writable data live, for both a source install and a PyInstaller exe."""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Folder holding `frontend/dist` and `browser-extension` (read-only resources)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def data_root() -> Path:
    """Folder for the database and .env. For an exe this is the folder containing the exe, so data
    survives restarts and is never written into a temporary extraction folder."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def system_worker_command() -> list[str]:
    """Command that runs one isolated hardware operation (see tools/system_worker.py)."""
    if is_frozen():
        return [sys.executable, "--system-worker"]
    return [sys.executable, "-m", "app.tools.system_worker"]
