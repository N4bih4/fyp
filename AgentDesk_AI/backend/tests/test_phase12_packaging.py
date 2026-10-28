"""Phase 12: packaging helpers (frozen-exe paths, hardware-worker command, release builder guards)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app import runtime

PROJECT = Path(__file__).resolve().parents[2]


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_release", PROJECT / "packaging" / "build_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------- runtime paths
def test_source_install_paths():
    assert not runtime.is_frozen()
    assert runtime.resource_root() == PROJECT
    assert runtime.data_root() == PROJECT / "backend"
    assert runtime.system_worker_command()[1:] == ["-m", "app.tools.system_worker"]


def test_frozen_exe_uses_bundle_for_resources_and_exe_folder_for_data(monkeypatch, tmp_path):
    bundle, exe_dir = tmp_path / "_internal", tmp_path / "AgentDeskAI"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "AgentDeskAI.exe"))
    assert runtime.resource_root() == bundle
    assert runtime.data_root() == exe_dir  # data must never live in the temporary/bundle folder
    assert runtime.system_worker_command() == [str(exe_dir / "AgentDeskAI.exe"), "--system-worker"]


def test_system_setting_tool_uses_the_frozen_aware_worker_command():
    source = (PROJECT / "backend" / "app" / "tools" / "system.py").read_text(encoding="utf-8")
    assert "system_worker_command()" in source and '"app.tools.system_worker"' not in source


def test_run_server_worker_mode_runs_one_isolated_operation_without_hardware():
    """`run_server.py --system-worker` must answer on stdout; bad input yields a clean failure, no server starts."""
    proc = subprocess.run([sys.executable, str(PROJECT / "backend" / "run_server.py"), "--system-worker"], input="not json",
                          capture_output=True, text=True, timeout=60, cwd=PROJECT / "backend")
    line = next((l for l in proc.stdout.splitlines() if l.startswith("AGENTX_RESULT=")), None)
    assert proc.returncode == 0 and line, proc.stderr[-300:]
    result = json.loads(line.removeprefix("AGENTX_RESULT="))
    assert result["success"] is False and "System worker failed" in result["error"]


# --------------------------------------------------------------- release builder
def test_builder_guard_regexes():
    builder = _load_builder()
    for bad in ("AgentDesk_AI/backend/.env", "AgentDesk_AI/backend/agentdesk.db", "x/agentdesk.log", "AgentDesk_AI/backend/.venv/Scripts/python.exe",
                "AgentDesk_AI/frontend/node_modules/x.js", "api_token", "cert.pem"):
        assert builder.FORBIDDEN.search(bad), bad
    for ok in ("AgentDesk_AI/.env.example", "AgentDesk_AI/backend/app/main.py", "AgentDesk_AI/frontend/dist/index.html"):
        assert not builder.FORBIDDEN.search(ok) or ok.endswith(".env.example"), ok
    assert builder.SECRET.search("key = gsk_" + "A" * 24) and builder.SECRET.search("sk-" + "b" * 40)
    assert not builder.SECRET.search("sk-short")


def test_builder_refuses_planted_secret_and_forbidden_files(tmp_path):
    builder = _load_builder()
    leaked = tmp_path / "notes.md"
    leaked.write_text("my key is gsk_" + "Z" * 30)
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=x")
    problems = builder.check([(leaked, "AgentDesk_AI/docs/notes.md"), (env_file, "AgentDesk_AI/backend/.env")])
    joined = " ".join(problems)
    assert "secret-shaped" in joined and "forbidden file" in joined and "missing required file" in joined


def test_real_package_contents_are_clean_and_complete():
    pytest.importorskip("zipfile")
    builder = _load_builder()
    files = builder.collect()
    names = {arc for _, arc in files}
    dist = PROJECT / "frontend" / "dist" / "index.html"
    if not dist.is_file():
        pytest.skip("frontend/dist not built")
    problems = builder.check(files)
    assert problems == [], problems
    assert not any("/tests/" in n or n.endswith((".db", ".log")) or "/.venv" in n for n in names)
    assert "AgentDesk_AI/backend/requirements.lock.txt" in names and "INSTALL.cmd" in names
