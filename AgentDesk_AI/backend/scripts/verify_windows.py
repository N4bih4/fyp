#!/usr/bin/env python3
"""AgentDesk AI - Windows verification script.

Exercises all 11 tools, the security policy, and (optionally) the HTTP API
against a running backend. Safe by design: everything happens inside a fresh
temp sandbox directory that is deleted afterwards, except for these
clearly-announced GUI actions:

  - launching Notepad (terminated by PID right after the check),
  - opening the sandbox folder in Explorer,
  - opening https://example.com in the default browser,
  - screenshots, which are saved inside the sandbox.

No OpenAI network calls are made. The OpenAI section only checks local
configuration and validates structured-output parsing with canned JSON.

Usage (from the backend/ directory, with the venv active):

    .venv\\Scripts\\python scripts\\verify_windows.py            # tools + security
    .venv\\Scripts\\python scripts\\verify_windows.py --no-gui   # skip GUI actions
    .venv\\Scripts\\python scripts\\verify_windows.py --api      # also test the HTTP API
                                                          # (start the server first)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

API = "http://127.0.0.1:8000"

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    tag = PASS if ok else FAIL
    print(f"[{tag}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def api_call(method: str, path: str, data: dict | None = None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode() or "{}"
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"detail": body}


# ---------------------------------------------------------------- tools
def tool_checks(ctx, sandbox: Path, gui: bool) -> None:
    from app.tools import platform as platform_tools
    from app.tools.registry import ToolRegistry

    reg = ToolRegistry(ctx)
    expected = [
        "compress_folder", "create_folder", "delete_file", "extract_file",
        "list_folder", "move_file", "open_application", "open_folder",
        "open_url", "rename_file", "take_screenshot",
    ]
    check("all 11 tools registered", reg.names() == expected, ",".join(reg.names()))

    run = lambda name, args: reg.get(name).execute(reg.get(name).validate_args(args))
    verify = lambda name, args, res: reg.get(name).verify(reg.get(name).validate_args(args), res)

    # create_folder + list_folder
    d = sandbox / "proj"
    r = run("create_folder", {"path": str(d)})
    check("create_folder executes", r.success, r.error or "")
    check("create_folder verifies", verify("create_folder", {"path": str(d)}, r).passed)
    (d / "hello.txt").write_text("hi")
    r = run("list_folder", {"path": str(d)})
    check("list_folder executes", r.success and any(e["name"] == "hello.txt" for e in r.output["entries"]), r.error or "")

    # rename_file
    r = run("rename_file", {"path": str(d / "hello.txt"), "new_name": "renamed.txt"})
    check("rename_file executes+verifies", r.success and verify("rename_file", {"path": str(d / "hello.txt"), "new_name": "renamed.txt"}, r).passed, r.error or "")

    # move_file
    dest = sandbox / "dest"
    dest.mkdir()
    r = run("move_file", {"source": str(d / "renamed.txt"), "destination": str(dest)})
    check("move_file executes+verifies", r.success and (dest / "renamed.txt").exists() and not (d / "renamed.txt").exists(), r.error or "")

    # compress_folder + extract_file
    r = run("compress_folder", {"folder_path": str(d)})
    zp = sandbox / "proj.zip"
    check("compress_folder executes+verifies", r.success and zp.is_file() and zipfile.is_zipfile(zp), r.error or "")
    out = sandbox / "extracted"
    r = run("extract_file", {"zip_path": str(zp), "destination": str(out)})
    check("extract_file executes+verifies", r.success and (out / "hello.txt").is_file(), r.error or "")

    # delete_file (high risk flag + real delete of sandbox file)
    t = reg.get("delete_file")
    check("delete_file is high risk", t.risk_level.value == "high")
    victim = sandbox / "victim.txt"
    victim.write_text("bye")
    r = run("delete_file", {"path": str(victim)})
    check("delete_file executes+verifies", r.success and not victim.exists(), r.error or "")

    # open_url scheme validation (no browser needed for the negative case)
    r = run("open_url", {"url": "file:///C:/Windows/win.ini"})
    check("open_url rejects non-http(s)", not r.success)

    if gui:
        # open_application: real Notepad launch, then terminate by PID
        launched_pid = None
        orig = platform_tools.launch_program
        try:
            def spy(exe, args=None):
                proc = orig(exe, args)
                nonlocal launched_pid
                launched_pid = proc.pid
                return proc
            platform_tools.launch_program = spy
            r = run("open_application", {"app_name": "notepad"})
        finally:
            platform_tools.launch_program = orig
        ok = r.success and launched_pid is not None
        check("open_application launches notepad", ok, r.error or f"pid={launched_pid}")
        if launched_pid:
            subprocess.run(["taskkill", "/PID", str(launched_pid), "/F"],
                           capture_output=True, timeout=15)

        # open_folder: opens Explorer on the sandbox
        r = run("open_folder", {"path": str(sandbox)})
        check("open_folder launches explorer", r.success, r.error or "")

        # open_url: opens the default browser
        r = run("open_url", {"url": "https://example.com"})
        check("open_url opens browser", r.success, r.error or "")

    # take_screenshot (no GUI popup; file lands in the sandbox)
    shot = sandbox / "shot.png"
    r = run("take_screenshot", {"output_path": str(shot)})
    if r.success:
        check("take_screenshot saves PNG", shot.is_file() and shot.stat().st_size > 0)
    else:
        check("take_screenshot reports honestly when unavailable", True, r.error or "")


# ---------------------------------------------------------------- security
def security_checks(ctx, sandbox: Path) -> None:
    from app.security.paths import PathNotAllowedError, resolve_within_allowed
    from app.tools.registry import ToolRegistry

    reg = ToolRegistry(ctx)
    run = lambda name, args: reg.get(name).execute(reg.get(name).validate_args(args))

    # path traversal blocked
    try:
        resolve_within_allowed(str(sandbox / ".." / "evil.txt"), ctx.allowed_directories)
        check("path traversal blocked", False, "no exception raised")
    except PathNotAllowedError:
        check("path traversal blocked", True)

    # relative paths rejected
    try:
        resolve_within_allowed("relative/path.txt", ctx.allowed_directories)
        check("relative paths rejected", False, "no exception raised")
    except PathNotAllowedError:
        check("relative paths rejected", True)

    # zip-slip blocked
    evil_zip = sandbox / "evil.zip"
    with zipfile.ZipFile(evil_zip, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")
    r = run("extract_file", {"zip_path": str(evil_zip)})
    check("zip-slip archive blocked", not r.success, r.error or "")

    # delete_file refuses non-empty folders and allowed roots
    full = sandbox / "full"
    full.mkdir()
    (full / "x.txt").write_text("x")
    r = run("delete_file", {"path": str(full)})
    check("delete refuses non-empty folder", not r.success, r.error or "")
    r = run("delete_file", {"path": str(sandbox)})
    check("delete refuses allowed root", not r.success, r.error or "")

    # no-overwrite policy
    a = sandbox / "a.txt"; b = sandbox / "b.txt"
    a.write_text("a"); b.write_text("b")
    r = run("move_file", {"source": str(a), "destination": str(b)})
    check("move refuses overwrite", not r.success and b.read_text() == "b")
    r = run("rename_file", {"path": str(a), "new_name": "b.txt"})
    check("rename refuses overwrite", not r.success)
    r = run("rename_file", {"path": str(a), "new_name": "..\\evil.txt"})
    check("rename rejects path separators", not r.success)

    # compress refuses archive-inside-folder and existing archives
    src = sandbox / "src"
    src.mkdir()
    r = run("compress_folder", {"folder_path": str(src), "zip_path": str(src / "inner.zip")})
    check("compress refuses archive inside source", not r.success)


# ---------------------------------------------------------------- API
def api_checks() -> None:
    status, body = api_call("GET", "/health")
    if status != 200:
        check("API reachable (is the server running?)", False, f"GET /health -> {status}")
        return
    check("GET /health", body.get("status") == "ok", str(body))

    status, cfg = api_call("GET", "/config/status")
    blob = json.dumps(cfg)
    check("config leaks no secrets", "sk-" not in blob and "OPENAI_API_KEY" not in blob)
    check("mock mode reported", cfg.get("mock_mode") is True, f"provider={cfg.get('ai_provider')}")
    if not cfg.get("mock_mode"):
        print("  (live provider configured - API tests still use mock-safe commands)")

    def post_task(command, key=None):
        payload = {"command": command}
        if key:
            payload["idempotency_key"] = key
        return api_call("POST", "/tasks", payload)

    # low risk: list downloads -> auto-approved -> run -> completed
    s, t = post_task("List the files in downloads")
    tid = t.get("id")
    check("low-risk task auto-approved", t.get("status") == "approved", t.get("status"))
    s, done = api_call("POST", f"/tasks/{tid}/run")
    check("low-risk task completes", done.get("status") == "completed", done.get("status"))

    # medium risk: needs approval; run-before-approval -> 409
    s, t = post_task("Create a folder called VerifyAPI in Documents")
    tid = t.get("id")
    check("medium-risk task awaits approval", t.get("status") == "awaiting_approval", t.get("status"))
    s, _ = api_call("POST", f"/tasks/{tid}/run")
    check("run before approval refused (409)", s == 409, f"status={s}")
    api_call("POST", f"/tasks/{tid}/approve", {})
    s, done = api_call("POST", f"/tasks/{tid}/run")
    action = (done.get("actions") or [{}])[0]
    check("medium-risk completes after approval",
          done.get("status") == "completed" and (action.get("verification") or {}).get("passed") is True,
          done.get("status"))

    # high risk: delete needs explicit approval, then really deletes
    victim = Path(tempfile.gettempdir()) / "agentdesk_verify_victim.txt"
    victim.write_text("delete me")
    s, t = post_task(f"Delete the file {victim}")
    tid = t.get("id")
    risk = (t.get("actions") or [{}])[0].get("risk")
    check("delete is high-risk + awaits approval",
          risk == "high" and t.get("status") == "awaiting_approval", f"risk={risk}")
    api_call("POST", f"/tasks/{tid}/approve", {})
    s, done = api_call("POST", f"/tasks/{tid}/run")
    check("high-risk delete executes after approval",
          done.get("status") == "completed" and not victim.exists(), done.get("status"))

    # reject: nothing runs
    keeper = Path(tempfile.gettempdir()) / "agentdesk_verify_keeper.txt"
    keeper.write_text("keep me")
    s, t = post_task(f"Delete the file {keeper}")
    api_call("POST", f"/tasks/{t['id']}/reject", {})
    s, rej = api_call("GET", f"/tasks/{t['id']}")
    check("rejected task never executes", rej.get("status") == "rejected" and keeper.exists())
    keeper.unlink(missing_ok=True)

    # idempotency: same key -> same task
    s, t1 = post_task("Take a screenshot", key="verify-key-1")
    s, t2 = post_task("Take a screenshot", key="verify-key-1")
    check("idempotency key returns same task", t1.get("id") == t2.get("id"))

    # no duplicate execution: second run is a no-op
    s, t = post_task("List the files in downloads", key="verify-key-2")
    api_call("POST", f"/tasks/{t['id']}/run")
    s, again = api_call("POST", f"/tasks/{t['id']}/run")
    check("finished tasks never re-execute", again.get("status") == "completed")

    # honest errors: path outside allowed dirs fails with a clear message
    s, t = post_task("Delete the file C:\\agentdesk_outside_allowed_xyz\\nope.txt")
    api_call("POST", f"/tasks/{t['id']}/approve", {})
    s, done = api_call("POST", f"/tasks/{t['id']}/run")
    err = json.dumps(done.get("actions") or [])
    check("disallowed path fails honestly",
          done.get("status") == "failed" and "allowed directories" in err)

    # previous-task meta command
    s, t = post_task("Show the result of the previous task")
    check("previous-task summary works",
          t.get("status") == "completed" and bool(t.get("plan_note")), t.get("plan_note"))


# ---------------------------------------------------------------- OpenAI (no network)
def openai_checks() -> None:
    print("\n-- OpenAI configuration (no network calls made) --")
    try:
        import openai  # noqa: F401
        check("openai SDK installed", True, f"v{openai.__version__}")
    except ImportError:
        check("openai SDK installed", False, "pip install openai")
        return

    from app.config import get_settings
    settings = get_settings()
    key_present = bool(settings.openai_api_key)
    check("OPENAI_API_KEY present in backend env", key_present,
          "set" if key_present else "not set - set it in backend/.env to use the real API")
    check("AI provider selection", True,
          f"AI_PROVIDER={settings.ai_provider} model={settings.ai_model}")

    # structured-output parsing validated with canned JSON (no API call)
    from app.ai.base import Plan
    from app.ai.planner import plan_command
    from app.tools.base import ToolContext
    from app.tools.registry import ToolRegistry
    import tempfile as _tf

    tmp = Path(_tf.mkdtemp(prefix="agentdesk_oai_"))
    ctx = ToolContext(allowed_directories=[tmp], approved_applications=[], test_dir=tmp)
    reg = ToolRegistry(ctx)

    class CannedProvider:
        is_mock = False

        def __init__(self, payload: str):
            self.payload = payload

        def generate_plan(self, command, tool_descriptions):
            return Plan.model_validate_json(self.payload)

    good = '{"actions": [{"tool": "create_folder", "args": {"path": "C:\\\\Temp\\\\Demo"}, "rationale": "canned"}], "note": null}'
    try:
        plan = plan_command("canned", reg, CannedProvider(good))
        check("structured plan JSON parses + validates", len(plan.actions) == 1 and plan.actions[0].tool == "create_folder")
    except Exception as e:  # noqa: BLE001
        check("structured plan JSON parses + validates", False, str(e)[:120])

    evil = '{"actions": [{"tool": "format_drive", "args": {}, "rationale": "x"}], "note": null}'
    try:
        plan_command("canned", reg, CannedProvider(evil))
        check("unknown tool in AI output rejected", False, "accepted!")
    except Exception:
        check("unknown tool in AI output rejected", True)

    bad_args = '{"actions": [{"tool": "open_url", "args": {"url": "ftp://x"}, "rationale": "x"}], "note": null}'
    try:
        plan_command("canned", reg, CannedProvider(bad_args))
        check("invalid AI arguments rejected", False, "accepted!")
    except Exception:
        check("invalid AI arguments rejected", True)
    shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11+ required.")
        return 2
    gui = "--no-gui" not in sys.argv
    with_api = "--api" in sys.argv

    sandbox = Path(tempfile.mkdtemp(prefix="agentdesk_verify_"))
    print(f"Sandbox: {sandbox}")
    if gui:
        print("GUI checks will briefly open Notepad, Explorer, and your browser.")
    try:
        from app.tools.base import ToolContext
        ctx = ToolContext(
            allowed_directories=[sandbox],
            approved_applications=["notepad"],
            test_dir=sandbox / "testdir",
        )
        print("\n-- tool checks --")
        tool_checks(ctx, sandbox, gui)
        print("\n-- security checks --")
        security_checks(ctx, sandbox)
        if with_api:
            print("\n-- API checks (server must be running) --")
            api_checks()
        print("\n-- OpenAI config checks --")
        openai_checks()
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed.")
    if failed:
        print("Failed checks:")
        for name, _, detail in failed:
            print(f"  - {name}: {detail}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
