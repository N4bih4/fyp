from pathlib import Path
from types import SimpleNamespace
import os
import pytest
from app.tools.filesystem import OpenFolderTool, FindPathsTool, DeleteFileTool, RestoreFileTool
from app.tools.packages import ApplicationPackageTool
from app.tools.base import RiskLevel


def test_duplicate_folder_never_opens_first_match(ctx, tmp_path, monkeypatch):
    for parent in ("lab", "college"):
        (tmp_path / parent / "lecture").mkdir(parents=True)
    monkeypatch.setattr("app.tools.platform.open_path_with_os", lambda p: pytest.fail("ambiguous folder opened"))
    tool = OpenFolderTool(ctx)
    result = tool.execute(tool.validate_args({"path": "lecture"}))
    assert not result.success
    assert result.output["needs_confirmation"]
    assert len(result.output["candidates"]) == 2


def test_search_preserves_unicode_names(ctx, tmp_path):
    name = "\u0644\u06cc\u06a9\u0686\u0631"
    (tmp_path / name).mkdir()
    tool = FindPathsTool(ctx)
    result = tool.execute(tool.validate_args({"name": name}))
    assert result.output["candidates"] == [str(tmp_path / name)]


@pytest.mark.parametrize("answer", ["yes", "haan kar do", "\u0939\u093e\u0901 \u0915\u0930 \u0926\u094b", "\u06c1\u0627\u06ba \u06a9\u0631 \u062f\u0648"])
def test_conversation_approval_is_bound_to_task(client, answer):
    """Rule 3: a spoken/typed yes approves medium risk; high risk needs the Approve click."""
    home = Path(os.environ["AGENTDESK_MOCK_HOME"])
    name = f"Conv{abs(hash(answer)) % 100000}"
    folder = home / "Documents" / name
    task = client.post("/tasks", json={"command": f"create a folder called {name} in Documents"}).json()
    assert task["status"] == "awaiting_approval" and task["actions"][0]["risk"] == "medium"
    response = client.post(f"/tasks/{task['id']}/reply", json={"message": answer})
    assert response.status_code == 200 and response.json()["status"] == "completed"
    assert folder.is_dir()
    assert client.post(f"/tasks/{task['id']}/reply", json={"message": "yes"}).status_code == 409

    target = home / "conversation-delete.txt"
    target.write_text("temporary")
    task = client.post("/tasks", json={"command": f"Delete the file {target}"}).json()
    assert task["status"] == "awaiting_approval" and task["actions"][0]["risk"] == "high"
    refused = client.post(f"/tasks/{task['id']}/reply", json={"message": answer}).json()
    assert refused["status"] == "awaiting_approval" and "click" in refused["plan_note"]
    assert target.exists(), "a voice yes must not delete"
    approved = client.post(f"/tasks/{task['id']}/approve", json={"action_ids": [task["actions"][0]["id"]]}).json()
    assert client.post(f"/tasks/{approved['id']}/run").json()["status"] == "completed"
    assert not target.exists()


def test_cancel_does_not_delete(client):
    home = Path(os.environ["AGENTDESK_MOCK_HOME"])
    target = home / "conversation-keep.txt"
    target.write_text("keep")
    task = client.post("/tasks", json={"command": f"Delete the file {target}"}).json()
    response = client.post(f"/tasks/{task['id']}/reply", json={"message": "no"})
    assert response.json()["status"] == "cancelled"
    assert target.exists()


def test_download_is_exact_and_does_not_run_installer(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.packages.platform.system", lambda: "Windows")
    monkeypatch.setattr("app.tools.packages.shutil.which", lambda _: "winget.exe")
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["shell"] is False
        destination = Path(command[command.index("--download-directory") + 1])
        (destination / "installer.exe").write_bytes(b"test")
        return SimpleNamespace(returncode=0, stdout="downloaded", stderr="")
    monkeypatch.setattr("app.tools.packages.subprocess.run", run)
    tool = ApplicationPackageTool(ctx)
    args = tool.validate_args({"action": "download", "query": "Microsoft.VisualStudioCode", "output_directory": str(tmp_path)})
    assert tool.risk_for_args(args) == RiskLevel.HIGH
    result = tool.execute(args)
    assert result.success
    assert result.output["installed"] is False
    assert len(calls) == 1
    assert calls[0][1] == "download"
    assert "--exact" in calls[0]


def test_nonempty_folder_trash_requires_explicit_flag(ctx, tmp_path):
    folder = tmp_path / "lectures"
    folder.mkdir()
    (folder / "notes.txt").write_text("important")
    tool = DeleteFileTool(ctx)
    assert not tool.execute(tool.validate_args({"path": str(folder)})).success
    result = tool.execute(tool.validate_args({"path": str(folder), "include_contents": True}))
    assert result.success
    assert result.output["restorable"]
    restore = RestoreFileTool(ctx)
    restored = restore.execute(restore.validate_args({"trash_id": result.output["trash_id"]}))
    assert restored.success
    assert (folder / "notes.txt").read_text() == "important"
