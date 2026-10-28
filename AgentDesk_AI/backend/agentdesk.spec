# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the AgentDesk AI Windows build (one-folder).

Build (from backend/, with the install's venv and `pip install pyinstaller`):
    python -m PyInstaller agentdesk.spec --noconfirm --distpath <out> --workpath <work>

Result: <out>\\AgentDeskAI\\AgentDeskAI.exe  (+ _internal). It serves the API AND the prebuilt web UI
on 127.0.0.1:8000. Build the UI first (`npm run build` in frontend/). One-folder is used instead of
one-file so the database/.env live next to the exe (not in a temp extraction folder) and start-up is fast.
Hardware tools run through `AgentDeskAI.exe --system-worker` (see run_server.py).
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

BACKEND = Path(SPECPATH)
PROJECT = BACKEND.parent

datas, binaries, hiddenimports = [], [], collect_submodules("app")
for _pkg in (
    "uvicorn", "fastapi", "starlette", "sqlalchemy", "pydantic", "pydantic_settings", "pydantic_core",
    "groq", "openai", "httpx", "httpcore", "anyio", "PIL", "websockets", "dotenv", "truststore",
    "pyautogui", "pygetwindow", "pymsgbox", "pyscreeze", "pytweening", "pyrect", "pyperclip",
    "pycaw", "comtypes", "screen_brightness_control", "winsdk", "wmi",
):
    try:
        _d, _b, _h = collect_all(_pkg)
    except Exception as exc:  # a missing optional package must not silently produce a broken exe
        raise SystemExit(f"Cannot bundle required package {_pkg!r}: {exc}")
    datas += _d
    binaries += _b
    hiddenimports += _h

# Static resources, resolved at run time through app.runtime.resource_root().
def _tree(source: Path, target: str, skip=("tests",)):
    items = []
    for path in source.rglob("*"):
        if path.is_file() and not any(part in skip for part in path.relative_to(source).parts):
            items.append((str(path), str(Path(target) / path.relative_to(source).parent)))
    return items

if not (PROJECT / "frontend" / "dist" / "index.html").is_file():
    raise SystemExit("frontend/dist is missing: run `npm run build` in frontend/ first.")
datas += _tree(PROJECT / "frontend" / "dist", "frontend/dist")
datas += _tree(PROJECT / "browser-extension", "browser-extension")

a = Analysis(
    ["run_server.py"],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="AgentDeskAI",
    debug=False,
    console=True,  # keep a console window for logs in this release
)
coll = COLLECT(exe, a.binaries, a.datas, name="AgentDeskAI")
