"""Test-only tools for the worker process (never registered in the product)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from pydantic import BaseModel

from app.tools.base import BaseTool, RiskLevel, ToolResult
from app.verification import failed_result, file_evidence, verdict


class SlowArgs(BaseModel):
    seconds: float = 30
    marker: str
    child_pid_file: str


class SlowTool(BaseTool):
    """Starts a grandchild process, then hangs. A timeout must kill both."""

    name = "slow_test_tool"
    description = "test only"
    risk_level = RiskLevel.LOW
    args_schema = SlowArgs

    def execute(self, args):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        Path(args.child_pid_file).write_text(str(child.pid))
        time.sleep(args.seconds)
        Path(args.marker).write_text("finished")
        return ToolResult(success=True, output={"marker": args.marker})

    def verify(self, args, result):
        if not result.success:
            return failed_result(result)
        return verdict([("marker written", Path(args.marker).exists())], file_evidence(args.marker))


class QuickArgs(BaseModel):
    path: str
    launch_child: bool = False


class QuickTool(BaseTool):
    """Writes its process id to a file; optionally leaves a long-lived child (like an opened app)."""

    name = "quick_test_tool"
    description = "test only"
    risk_level = RiskLevel.LOW
    args_schema = QuickArgs

    def execute(self, args):
        child_pid = None
        if args.launch_child:
            child_pid = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"]).pid
        Path(args.path).write_text(str(os.getpid()))
        return ToolResult(success=True, output={"path": args.path, "worker_pid": os.getpid(), "child_pid": child_pid})

    def verify(self, args, result):
        if not result.success:
            return failed_result(result)
        return verdict([("file written", Path(args.path).is_file())], file_evidence(args.path))
