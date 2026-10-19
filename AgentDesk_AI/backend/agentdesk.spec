# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the AgentDesk AI backend (Windows only).

Build ONLY after the app is verified working on Windows:
    1. scripts/verify_windows.py --api   (all checks green)
    2. .\\build_windows.ps1

The resulting dist\\AgentDeskAI.exe serves the API on 127.0.0.1:8000.
Serve frontend/dist with any static server (or the same exe in future).
"""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for _pkg in (
    "uvicorn", "fastapi", "starlette", "sqlalchemy",
    "pydantic", "pydantic_settings", "openai", "PIL", "anyio",
    "pycaw", "screen_brightness_control", "winsdk",
):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

a = Analysis(
    ["run_server.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="AgentDeskAI",
    debug=False,
    console=True,  # keep console for logs in v1; set False later with file logging
)
