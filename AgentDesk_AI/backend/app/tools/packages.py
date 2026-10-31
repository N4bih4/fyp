"""Windows Package Manager: search, show and download (application_package); install by exact ID only
after explicit approval (winget_install, verified with `winget list`)."""
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
    timeout_seconds = 250  # WinGet downloads; the child winget is killed with the worker
    interruptible = True
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




# ------------------------------------------------------------------ install (Phase 18)
WINGET_ID = r"^[A-Za-z0-9][A-Za-z0-9._+-]{1,127}$"


class WingetInstallArgs(BaseModel):
    package_id: str = Field(pattern=WINGET_ID, description="Exact WinGet package ID from a search, e.g. VideoLAN.VLC")
    source: Literal["winget", "msstore"] = "winget"


def run_winget(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run winget without a console window. Tests replace this function."""
    executable = shutil.which("winget")
    if platform.system() != "Windows" or not executable:
        raise FileNotFoundError("WinGet was not found. Install/update Microsoft's App Installer, then retry.")
    return subprocess.run([executable, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def is_installed(package_id: str) -> tuple[bool, str]:
    """`winget list --id X --exact`: exit 0 and the ID in the table means installed."""
    listed = run_winget(["list", "--id", package_id, "--exact", "--accept-source-agreements",
                         "--disable-interactivity"], timeout=60)
    text = (listed.stdout or "") + (listed.stderr or "")
    return listed.returncode == 0 and package_id.casefold() in text.casefold(), text[-2000:]


class WingetInstallTool(BaseTool):
    name = "winget_install"
    description = ("Install one Windows app by its exact WinGet package ID (from application_package search). "
                   "High risk: shown for explicit approval with the package ID and source; accepts the package's "
                   "license agreement on approval. Windows may still show its own administrator prompt.")
    args_schema = WingetInstallArgs
    risk_level = RiskLevel.HIGH
    timeout_seconds = 900
    interruptible = False  # a killed installer leaves a half-installed app; it always finishes

    def execute(self, args: BaseModel) -> ToolResult:
        a = WingetInstallArgs.model_validate(args.model_dump())
        try:
            already, listing = is_installed(a.package_id)
            if already:
                return ToolResult(success=True, output={"package_id": a.package_id, "already_installed": True,
                                                        "installed": True, "details": listing[-1500:]})
            result = run_winget(["install", "--id", a.package_id, "--exact", "--source", a.source,
                                 "--accept-package-agreements", "--accept-source-agreements",
                                 "--disable-interactivity", "--silent"], timeout=self.timeout_seconds - 60)
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=str(exc))
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="WinGet did not finish in time; check Apps & features before retrying.")
        details = ((result.stdout or "") + (result.stderr or ""))[-6000:]
        if result.returncode != 0:
            return ToolResult(success=False, output={"details": details, "exit_code": result.returncode},
                              error=f"WinGet install failed (exit {result.returncode}). See details; an admin prompt may have been declined.")
        return ToolResult(success=True, output={"package_id": a.package_id, "already_installed": False,
                                                "exit_code": 0, "details": details})

    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        """A fresh `winget list --id <id> --exact` must show the package."""
        if not result.success:
            return failed_result(result)
        a = WingetInstallArgs.model_validate(args.model_dump())
        try:
            installed, listing = is_installed(a.package_id)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return Verification(passed=False, checks=["winget list could not run"], details=str(exc))
        return verdict([("winget list shows the package", installed)],
                       {"package_id": a.package_id, "winget_list_tail": listing[-600:],
                        "already_installed": result.output.get("already_installed")})


def package_tools(ctx=None) -> list[BaseTool]:
    return [ApplicationPackageTool(ctx), WingetInstallTool(ctx)]
