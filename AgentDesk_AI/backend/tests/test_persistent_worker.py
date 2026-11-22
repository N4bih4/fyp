"""The system worker stays alive between requests (volume / brightness): the 3-second Python start-up is paid once."""
from __future__ import annotations

import sys
import textwrap

from app.tools import system
from app.tools.base import ToolResult

FAKE = textwrap.dedent('''
    import sys, json
    n = 0
    for line in sys.stdin:
        n += 1
        print("AGENTX_RESULT=" + json.dumps({"success": True, "output": {"call": n, "got": line.strip()[:20]}, "error": None}), flush=True)
''')


def test_one_process_answers_many_requests_and_is_restarted_when_it_dies(monkeypatch, tmp_path):
    script = tmp_path / "fake_worker.py"
    script.write_text(FAKE)
    monkeypatch.setattr(system, "system_worker_command", lambda: [sys.executable, str(script)])
    monkeypatch.setattr(system, "data_root", lambda: tmp_path)
    worker = system._PersistentWorker()
    try:
        first = worker.call('{"setting": "volume", "action": "get"}')
        second = worker.call('{"setting": "volume", "action": "get"}')
        assert isinstance(first, ToolResult) and first.output["call"] == 1 and second.output["call"] == 2      # the same process counted 1 then 2
        worker._proc.kill()
        worker._proc.wait()
        third = worker.call('{"setting": "volume", "action": "get"}')
        assert third.output["call"] == 1                                                                         # a fresh process
    finally:
        worker.stop()


def test_a_worker_that_does_not_answer_gives_up_so_the_one_shot_path_runs(monkeypatch, tmp_path):
    script = tmp_path / "silent_worker.py"
    script.write_text("import sys\nfor line in sys.stdin:\n    pass\n")
    monkeypatch.setattr(system, "system_worker_command", lambda: [sys.executable, str(script)])
    monkeypatch.setattr(system, "data_root", lambda: tmp_path)
    worker = system._PersistentWorker()
    assert worker.call('{"setting": "volume", "action": "get"}', timeout=1.0) is None
    assert worker._proc is None                                                                                  # killed, will restart on the next call


def test_stopping_the_workers_leaves_no_process_behind(monkeypatch, tmp_path):
    script = tmp_path / "fake_worker.py"
    script.write_text(FAKE)
    monkeypatch.setattr(system, "system_worker_command", lambda: [sys.executable, str(script)])
    monkeypatch.setattr(system, "data_root", lambda: tmp_path)
    workers = {"write": system._PersistentWorker(), "read": system._PersistentWorker()}
    monkeypatch.setattr(system, "_WORKERS", workers)
    for worker in workers.values():
        worker.call('{"setting": "volume", "action": "get"}')
    procs = [w._proc for w in workers.values()]
    system.stop_workers()
    for proc in procs:
        proc.wait(timeout=5)
        assert proc.poll() is not None
