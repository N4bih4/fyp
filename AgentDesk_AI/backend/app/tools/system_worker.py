"""One bounded Windows hardware operation on the process's main COM thread.

One-shot (default): read one request from stdin, print one `AGENTX_RESULT=` line, exit. Serving (`--serve`): the same, once per input line until stdin
closes, so the Python start-up and the audio / WMI imports (about 3 seconds) are paid once instead of for every "volume kam karo".
"""
import sys
from .base import ToolContext, ToolResult
from .system import ManageSystemSettingArgs, ManageSystemSettingTool


def _run(raw: str) -> ToolResult:
    try:
        args = ManageSystemSettingArgs.model_validate_json(raw)
        return ManageSystemSettingTool(ToolContext())._execute(args)
    except Exception as exc:
        return ToolResult(success=False, error=f"System worker failed: {type(exc).__name__}")


def main():
    if "--serve" in sys.argv:
        for line in sys.stdin:
            if line.strip():
                print("AGENTX_RESULT=" + _run(line.strip()[:8192]).model_dump_json(), flush=True)
        return
    print("AGENTX_RESULT=" + _run(sys.stdin.read(8192)).model_dump_json(), flush=True)


if __name__ == "__main__":
    main()
