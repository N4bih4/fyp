"""Checkpoints and verified rollback for file-changing tools.

Before a supported tool runs, `capture` records the pre-state (and backs up a
file that is about to be overwritten). After it succeeds, `finalize` stores a
rollback plan with content fingerprints. `perform` undoes the action only if
the result is still exactly what the action produced, and reports success only
after re-checking the filesystem. Anything else (system settings, desktop
input, launches, uploads) is explicitly "unsupported".
"""
from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path

from ..security.paths import resolve_within_allowed

MAX_BACKUP_BYTES = 20 * 1024 * 1024
MAX_TREE_FILES = 5000
BACKUP_DIR_NAME = ".agentdesk_checkpoints"

SUPPORTED_TOOLS = {
    "create_folder", "move_file", "rename_file", "copy_file", "compress_folder", "extract_file",
    "write_text_file", "edit_text_file", "delete_file", "download_web_content",
}


class CheckpointError(RuntimeError):
    """The pre-state could not be saved, so the action must not run."""


# ------------------------------------------------------------------ helpers
def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(path: Path) -> str | None:
    """Content hash of a file, or of a whole folder tree (names + contents)."""
    if path.is_symlink():
        return None
    if path.is_file():
        return _sha(path)
    if path.is_dir():
        digest = hashlib.sha256()
        count = 0
        for folder, dirs, files in os.walk(path, followlinks=False):
            dirs.sort()
            for name in sorted(files):
                count += 1
                if count > MAX_TREE_FILES:
                    return None
                item = Path(folder) / name
                digest.update(str(item.relative_to(path)).encode("utf-8", "replace") + b"\0")
                digest.update(_sha(item).encode())
        return digest.hexdigest()
    return None


def _inside(raw: str, ctx) -> Path:
    return resolve_within_allowed(raw, ctx.allowed_directories)


def _backup_root(ctx) -> Path:
    if not ctx.allowed_directories:
        raise CheckpointError("No allowed directory is available for checkpoints")
    return Path(ctx.allowed_directories[0]).expanduser().resolve() / BACKUP_DIR_NAME


def _backup_file(source: Path, ctx) -> str:
    try:
        if source.stat().st_size > MAX_BACKUP_BYTES:
            raise CheckpointError(f"{source.name} is larger than {MAX_BACKUP_BYTES // (1024 * 1024)} MB; cannot create a rollback checkpoint")
        folder = _backup_root(ctx) / uuid.uuid4().hex
        folder.mkdir(parents=True, exist_ok=False)
        target = folder / "content.bak"
        shutil.copy2(source, target)
        if _sha(target) != _sha(source):
            raise CheckpointError("Checkpoint copy did not match the original; action not run")
        return str(target)
    except OSError as exc:
        raise CheckpointError(f"Could not create rollback checkpoint: {exc}") from exc


# ------------------------------------------------------------------ capture
def capture(tool_name: str, parsed, ctx) -> dict:
    """Record pre-state. Raises CheckpointError when a needed backup cannot be made."""
    pre: dict = {}
    try:
        if tool_name in {"write_text_file", "edit_text_file"}:
            target = _inside(parsed.path, ctx)
            pre["existed"] = target.exists()
            if target.is_file():
                pre["backup"] = _backup_file(target, ctx)
                pre["before_sha"] = _sha(target)
        elif tool_name == "create_folder":
            target = Path(parsed.path).expanduser()
            missing = []
            probe = target
            while not probe.exists() and probe != probe.parent:
                missing.append(str(probe))
                probe = probe.parent
            pre["missing_dirs"] = missing  # deepest first
        elif tool_name == "extract_file":
            dest = Path(parsed.destination).expanduser() if parsed.destination else Path(str(Path(parsed.zip_path).with_suffix("")) + "_extracted")
            pre["dest_existed"] = dest.exists()
        elif tool_name in {"copy_file", "move_file", "compress_folder", "download_web_content", "rename_file", "delete_file"}:
            pre["noted"] = True
    except ValueError:
        pass  # path outside allowed dirs: the tool itself will refuse
    return pre


# ----------------------------------------------------------------- finalize
def finalize(tool_name: str, parsed, output: dict, pre: dict, ctx) -> dict | None:
    """Return a rollback plan for a successful action, or None when unsupported."""
    try:
        if tool_name == "create_folder":
            if output.get("already_existed"):
                return {"kind": "nothing", "reason": "folder already existed"}
            return {"kind": "remove_empty_dirs", "dirs": pre.get("missing_dirs") or [output["path"]]}
        if tool_name in {"move_file", "rename_file"}:
            src = output.get("source") or output.get("old_path")
            dst = output.get("destination") or output.get("new_path")
            return {"kind": "move_back", "from": dst, "to": src, "sha": fingerprint(Path(dst))}
        if tool_name in {"copy_file", "compress_folder", "download_web_content"}:
            created = output.get("destination") or output.get("zip_path") or output.get("path")
            fp = fingerprint(Path(created))
            return {"kind": "remove_created", "path": created, "sha": fp} if fp else None
        if tool_name == "extract_file":
            dest = Path(output["destination"])
            files = []
            for name in output.get("files", []):
                if name.endswith("/"):
                    continue
                item = dest / name
                files.append({"path": str(item), "sha": _sha(item)})
            return {"kind": "remove_files", "files": files, "dest": str(dest), "remove_dest": not pre.get("dest_existed", True)}
        if tool_name in {"write_text_file", "edit_text_file"}:
            path = Path(output["path"])
            after = _sha(path)
            if pre.get("backup"):
                return {"kind": "restore_backup", "path": str(path), "backup": pre["backup"],
                        "before_sha": pre["before_sha"], "after_sha": after}
            return {"kind": "remove_created", "path": str(path), "sha": after}
        if tool_name == "delete_file":
            return {"kind": "restore_trash", "trash_id": output["trash_id"], "path": output["deleted"]}
    except (KeyError, OSError, TypeError):
        return None
    return None


# ------------------------------------------------------------------ perform
def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def perform(plan: dict, ctx) -> tuple[bool, str]:
    """Undo one action. Returns (verified_success, detail); never raises for expected conditions."""
    kind = plan.get("kind")
    try:
        if kind == "nothing":
            return True, plan.get("reason", "nothing to undo")

        if kind == "remove_empty_dirs":
            removed = []
            for raw in plan["dirs"]:
                path = Path(raw)
                if not path.exists():
                    continue
                if not path.is_dir() or any(path.iterdir()):
                    return False, f"{path} is not empty now; left in place"
                path.rmdir()
                removed.append(str(path))
            still = [d for d in plan["dirs"] if Path(d).exists()]
            return (not still), (f"removed {len(removed)} folder(s)" if not still else f"still exists: {still}")

        if kind == "move_back":
            src, dst = _inside(plan["from"], ctx), _inside(plan["to"], ctx)
            if not src.exists():
                return False, f"{src} no longer exists; cannot move it back"
            if dst.exists():
                return False, f"{dst} already exists; refusing to overwrite"
            if plan.get("sha") and fingerprint(src) != plan["sha"]:
                return False, f"{src} changed after the action; refusing to move it back"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            ok = dst.exists() and not src.exists()
            return ok, "moved back" if ok else "move-back could not be verified"

        if kind == "remove_created":
            path = _inside(plan["path"], ctx)
            if not path.exists():
                return True, "already gone"
            if fingerprint(path) != plan["sha"]:
                return False, f"{path.name} changed after the action; refusing to delete it"
            _remove_path(path)
            return (not path.exists()), "removed" if not path.exists() else "still exists"

        if kind == "remove_files":
            files = [(_inside(f["path"], ctx), f["sha"]) for f in plan["files"]]
            for path, sha in files:  # verify everything before deleting anything
                if path.exists() and _sha(path) != sha:
                    return False, f"{path.name} changed after extraction; nothing was removed"
            for path, _ in files:
                if path.exists():
                    path.unlink()
            dest = _inside(plan["dest"], ctx)
            for folder, dirs, _f in os.walk(dest, topdown=False):
                if not any(Path(folder).iterdir()) and (Path(folder) != dest or plan.get("remove_dest")):
                    Path(folder).rmdir()
            left = [str(p) for p, _ in files if p.exists()]
            return (not left), "extracted files removed" if not left else f"still present: {left}"

        if kind == "restore_backup":
            path, backup = _inside(plan["path"], ctx), Path(plan["backup"])
            if not backup.is_file() or _sha(backup) != plan["before_sha"]:
                return False, "checkpoint copy is missing or damaged"
            if not path.is_file() or _sha(path) != plan["after_sha"]:
                return False, f"{path.name} changed after the action; refusing to overwrite it"
            shutil.copy2(backup, path)
            ok = _sha(path) == plan["before_sha"]
            return ok, "previous content restored" if ok else "restore could not be verified"

        if kind == "restore_trash":
            from ..tools.filesystem import RestoreFileArgs, RestoreFileTool

            result = RestoreFileTool(ctx).execute(RestoreFileArgs(trash_id=plan["trash_id"]))
            if not result.success:
                return False, result.error or "restore failed"
            restored = Path(result.output["restored"]).exists()
            return restored, "restored from Trash" if restored else "restore could not be verified"
    except (OSError, ValueError, KeyError) as exc:
        return False, f"rollback failed: {exc}"
    return False, f"unsupported rollback kind {kind!r}"
