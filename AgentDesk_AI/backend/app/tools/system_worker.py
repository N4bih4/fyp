"""One bounded Windows hardware operation on the process's main COM thread."""
import sys
from .base import ToolContext, ToolResult
from .system import ManageSystemSettingArgs, ManageSystemSettingTool


def main():
    try:
        args = ManageSystemSettingArgs.model_validate_json(sys.stdin.read(8192))
        result = ManageSystemSettingTool(ToolContext())._execute(args)
    except Exception as exc:
        result = ToolResult(success=False, error=f"System worker failed: {type(exc).__name__}")
    print("AGENTX_RESULT=" + result.model_dump_json(), flush=True)


if __name__ == "__main__":
    main()
