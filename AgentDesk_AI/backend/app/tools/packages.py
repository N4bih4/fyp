"""Windows Package Manager discovery and download, without running installers."""
from __future__ import annotations
import platform
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from ..security.paths import resolve_within_allowed
from ..verification import failed_result, file_evidence, verdict
from .base import BaseTool, RiskLevel, ToolResult, Verification


class PackageArgs(BaseModel):
    action: Literal["search", "show", "download"]
    query: str = Field(min_length=1, max_length=150, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._+()-]*$")
    source: Literal["winget", "msstore"] = "winget"
    output_directory: str | None = None


class ApplicationPackageTool(BaseTool):
    name = "application_package"
    description = ("Search available Windows apps (including VS Code and WhatsApp), show an exact package ID, "
                   "or download its installer after approval. Search first, show publisher/details, clarify ambiguous matches. "
                   "For show/download query MUST be the exact ID returned by search. Source winget or msstore. "
                   "Download does not install or launch; some Store apps require Store sign-in or cannot be downloaded.")
    args_schema = PackageArgs
    risk_level = RiskLevel.HIGH

    def risk_for_args(self, args):
        return RiskLevel.HIGH if args is None or args.action == "download" else RiskLevel.LOW

    def execute(self, args):
        a = PackageArgs.model_validate(args.model_dump())
        if platform.system() != "Windows":
            return ToolResult(success=False, error="Application downloads require Windows Package Manager.")
        executable = shutil.which("winget")
        if not executable:
            return ToolResult(success=False, error="WinGet was not found. Install/update Microsoft's App Installer, then retry.")
        command = [executable, a.action]
        if a.action == "search":
            command += ["--query", a.query]
        else:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", a.query):
                return ToolResult(success=False, error="Use an exact package ID from search results.")
            command += ["--id", a.query, "--exact"]
        destination = None
        if a.action == "download":
            try:
                base = a.output_directory or str(Path.home() / "Downloads")
                destination = resolve_within_allowed(str(Path(base).expanduser() / (a.query + "-" + uuid.uuid4().hex[:8])), self.ctx.allowed_directories)
                destination.mkdir(parents=True, exist_ok=False)
            except (ValueError, OSError) as exc:
                return ToolResult(success=False, error=str(exc))
            command += ["--download-directory", str(destination)]
        command += ["--source", a.source, "--disable-interactivity"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=240 if destination else 20, shell=False,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="WinGet timed out; download may be incomplete. Retry explicitly.")
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not start WinGet: {exc}")
        output = {"details": (result.stdout + result.stderr)[-14000:], "installed": False}
        if destination:
            files = [str(p) for p in destination.rglob("*") if p.is_file()]
            output.update(directory=str(destination), files=files)
            if not files and result.returncode == 0:
                return ToolResult(success=False, output=output, error="WinGet reported success but no downloaded files were found.")
        return ToolResult(success=result.returncode == 0, output=output,
                          error=None if result.returncode == 0 else "WinGet failed. Review package details, agreements, Store sign-in, or App Installer version in the output.")

    def verify(self, args, result: ToolResult) -> Verification:
        if not result.success:
            return failed_result(result)
        out = result.output or {}
        if out.get("directory"):
            files = [Path(f) for f in out.get("files", [])]
            return verdict([("downloaded files exist", bool(files) and all(f.is_file() for f in files))],
                           {"directory": out["directory"], "files": [file_evidence(f) for f in files[:3]]})
        details = str(out.get("details", ""))
        return verdict([("WinGet exited 0 and printed results", bool(details.strip()))],
                       {"winget_output_chars": len(details), "installed": out.get("installed")})


