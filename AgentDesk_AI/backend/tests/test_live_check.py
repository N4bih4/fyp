"""scripts/live_check.py: every registered tool has a probe; sandbox probes pass for real."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app.tools.registry import ToolRegistry

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "live_check.py"
spec = importlib.util.spec_from_file_location("live_check", SCRIPT)
live_check = importlib.util.module_from_spec(spec)
sys.modules["live_check"] = live_check  # dataclasses need the module registered
spec.loader.exec_module(live_check)


def test_every_registered_tool_has_exactly_one_probe():
    probes = [p.tool for p in live_check.PROBES]
    assert len(probes) == len(set(probes))
    assert set(probes) == set(ToolRegistry().names())
    assert {p.category for p in live_check.PROBES} <= set(live_check.CATEGORIES)


def test_no_probe_changes_system_settings_or_sends_input():
    import inspect

    source = inspect.getsource(live_check)
    for forbidden in ('"action": "set"', '"action": "off"', '"action": "on"', "type_text", "close_window",
                      '"action": "close"', '"action": "download"'):
        assert forbidden not in source


def test_sandbox_probes_pass_and_every_tool_is_reported(tmp_path):
    rows = live_check.run_checks({"sandbox"}, sandbox=tmp_path / "sb")
    assert {r["tool"] for r in rows} == set(ToolRegistry().names())
    sandbox_rows = [r for r in rows if r["category"] == "sandbox"]
    assert len(sandbox_rows) == 15
    failed = [r for r in sandbox_rows if r["status"] != live_check.PASS]
    assert not failed, failed
    assert all(r["status"] == live_check.SKIP for r in rows if r["category"] != "sandbox")
    # Evidence comes from an independent check, not just the tool's own message.
    assert all(r["evidence"] for r in rows)


def test_missing_probe_is_reported_as_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(live_check, "PROBES", [p for p in live_check.PROBES if p.tool != "list_trash"])
    rows = live_check.run_checks({"sandbox"}, sandbox=tmp_path / "sb")
    row = next(r for r in rows if r["tool"] == "list_trash")
    assert row["status"] == live_check.FAIL and "no live probe" in row["evidence"]
