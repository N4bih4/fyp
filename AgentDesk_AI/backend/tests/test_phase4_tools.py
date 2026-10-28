"""Phase 4: tool safety regressions. Disposable temp data only; no OS launches, no Wi-Fi/Bluetooth."""
from __future__ import annotations

import sys
import types
import zipfile
from pathlib import Path

import pytest

from app.tools import filesystem as fs
from app.tools import platform as _platform
from app.tools.base import RiskLevel
from app.tools.desktop import DesktopControlArgs, DesktopControlTool, is_shell_target


# ------------------------------------------------------------ shell policy
@pytest.mark.parametrize("title,process,expected", [
    ("Windows PowerShell", None, True),
    ("Administrator: Command Prompt", None, True),
    ("anything", "WindowsTerminal.exe", True),
    ("Run", None, True),
    ("Task Manager", None, True),
    ("bash - ubuntu", None, True),
    ("Untitled - Notepad", "notepad.exe", False),
    ("Google Chrome", "chrome.exe", False),
    ("Terminal-style report.docx - Word", "winword.exe", True),  # conservative: title word match
])
def test_is_shell_target(title, process, expected):
    assert is_shell_target(title, process) is expected


def _args(target, *steps):
    return DesktopControlArgs.model_validate({"target_window": target, "steps": list(steps)})


def test_typing_into_named_shell_is_never_auto_approved():
    a = _args("Windows PowerShell", {"action": "type_text", "text": "whoami"})
    assert DesktopControlTool.risk_for_user_command(a, "type in powershell hello") == RiskLevel.HIGH


def test_typing_into_named_normal_app_still_auto_approved():
    a = _args("Untitled - Notepad", {"action": "type_text", "text": "hello"})
    assert DesktopControlTool.risk_for_user_command(a, "type hello in notepad") == RiskLevel.LOW


def test_closing_a_named_shell_window_is_still_allowed_by_policy():
    a = _args("Windows PowerShell", {"action": "close_window"})
    assert DesktopControlTool.risk_for_user_command(a, "close powershell") == RiskLevel.LOW


def _fake_pyautogui(monkeypatch, title):
    window = types.SimpleNamespace(title=title, _hWnd=None)
    sent = []
    mod = types.ModuleType("pyautogui")
    mod.FAILSAFE = True
    mod.getAllWindows = lambda: [window]
    mod.getActiveWindow = lambda: window
    mod.size = lambda: (1920, 1080)
    mod.write = lambda *a, **k: sent.append(("write", a))
    mod.press = lambda *a, **k: sent.append(("press", a))
    mod.hotkey = lambda *a, **k: sent.append(("hotkey", a))
    mod.click = lambda *a, **k: sent.append(("click", a))
    monkeypatch.setitem(sys.modules, "pyautogui", mod)
    return sent


def test_execute_refuses_input_to_shell_even_if_approved(monkeypatch, ctx):
    sent = _fake_pyautogui(monkeypatch, "Windows PowerShell")
    result = DesktopControlTool(ctx).execute(_args("Windows PowerShell", {"action": "type_text", "text": "whoami"}))
    assert result.success is False and "Refused" in result.error
    assert sent == []


def test_execute_still_types_into_normal_window(monkeypatch, ctx):
    sent = _fake_pyautogui(monkeypatch, "Untitled - Notepad")
    result = DesktopControlTool(ctx).execute(_args("Untitled - Notepad", {"action": "type_text", "text": "hi"}))
    assert result.success is True and sent and sent[0][0] == "write"


# --------------------------------------------------------------- filesystem
@pytest.fixture()
def no_launch(monkeypatch):
    opened = []
    monkeypatch.setattr(_platform, "open_path_with_os", lambda p: opened.append(p))
    return opened


@pytest.mark.parametrize("name", ["run.bat", "x.EXE", "s.ps1", "m.vbs", "l.lnk", "t.py", "a.js", "i.msi"])
def test_open_file_refuses_executable_types(ctx, tmp_path, no_launch, name):
    f = tmp_path / name
    f.write_text("echo hi")
    result = fs.OpenFileTool(ctx).execute(fs.OpenFileArgs(path=str(f)))
    assert result.success is False and "run code" in result.error
    assert no_launch == []


def test_open_file_still_opens_documents(ctx, tmp_path, no_launch):
    f = tmp_path / "notes.txt"
    f.write_text("hi")
    assert fs.OpenFileTool(ctx).execute(fs.OpenFileArgs(path=str(f))).success is True
    assert no_launch == [str(f.resolve())]


def test_write_text_file_cannot_author_scripts(ctx, tmp_path):
    result = fs.WriteTextFileTool(ctx).execute(fs.WriteTextFileArgs(path=str(tmp_path / "x.bat"), content="calc"))
    assert result.success is False and not (tmp_path / "x.bat").exists()
    ok = fs.WriteTextFileTool(ctx).execute(fs.WriteTextFileArgs(path=str(tmp_path / "x.txt"), content="ok"))
    assert ok.success is True


def test_allowed_root_cannot_be_moved_or_renamed(ctx, tmp_path):
    moved = fs.MoveFileTool(ctx).execute(fs.MoveFileArgs(source=str(tmp_path), destination=str(tmp_path / "inside")))
    assert moved.success is False and "allowed root" in moved.error
    renamed = fs.RenameFileTool(ctx).execute(fs.RenameFileArgs(path=str(tmp_path), new_name="other"))
    assert renamed.success is False and tmp_path.exists()


def test_rename_rejects_alternate_data_stream_names(ctx, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    result = fs.RenameFileTool(ctx).execute(fs.RenameFileArgs(path=str(f), new_name="a.txt:evil.bat"))
    assert result.success is False and f.exists()


def _zip(path: Path, files: dict[str, str]):
    with zipfile.ZipFile(path, "w") as z:
        for name, body in files.items():
            z.writestr(name, body)


def test_extract_refuses_to_overwrite_existing_files(ctx, tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "a.txt").write_text("ORIGINAL")
    _zip(tmp_path / "z.zip", {"a.txt": "NEW", "b.txt": "B"})
    result = fs.ExtractFileTool(ctx).execute(fs.ExtractFileArgs(zip_path=str(tmp_path / "z.zip"), destination=str(dest)))
    assert result.success is False
    assert (dest / "a.txt").read_text() == "ORIGINAL" and not (dest / "b.txt").exists()


def test_extract_blocks_zip_slip(ctx, tmp_path):
    _zip(tmp_path / "evil.zip", {"../escape.txt": "x"})
    result = fs.ExtractFileTool(ctx).execute(fs.ExtractFileArgs(zip_path=str(tmp_path / "evil.zip"), destination=str(tmp_path / "o")))
    assert result.success is False and not (tmp_path / "escape.txt").exists()


def test_extract_enforces_entry_limit(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "MAX_EXTRACT_ENTRIES", 2)
    _zip(tmp_path / "many.zip", {f"f{i}.txt": "x" for i in range(3)})
    result = fs.ExtractFileTool(ctx).execute(fs.ExtractFileArgs(zip_path=str(tmp_path / "many.zip"), destination=str(tmp_path / "o2")))
    assert result.success is False and "too large" in result.error


def test_extract_normal_archive_works(ctx, tmp_path):
    _zip(tmp_path / "ok.zip", {"a.txt": "A", "sub/b.txt": "B"})
    result = fs.ExtractFileTool(ctx).execute(fs.ExtractFileArgs(zip_path=str(tmp_path / "ok.zip"), destination=str(tmp_path / "o3")))
    assert result.success is True and (tmp_path / "o3" / "sub" / "b.txt").read_text() == "B"
