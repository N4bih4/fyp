"""Actual-PC checks. Default is read-only; --change-controls restores original states.

Never toggles Wi-Fi. No destructive filesystem tests or cloud calls.
Run with the backend virtual environment from this directory.
"""
import argparse
import json
from app.tools.base import ToolContext
from app.tools.system import ManageSystemSettingTool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--change-controls", action="store_true")
    args = parser.parse_args()
    tool = ManageSystemSettingTool(ToolContext(isolate_system_controls=True))
    failures = []

    def invoke(setting, action, **extra):
        result = tool.execute(tool.validate_args(dict(setting=setting, action=action, **extra)))
        print(json.dumps({"setting": setting, "action": action, **result.model_dump()}, ensure_ascii=True), flush=True)
        if not result.success:
            failures.append(f"{setting}/{action}")
        return result

    for setting in ("volume", "brightness", "bluetooth", "wifi"):
        original = invoke(setting, "get")
        if not args.change_controls or setting == "wifi" or not original.success:
            continue
        if setting == "bluetooth":
            restore = "on" if original.output["enabled"] else "off"
            try:
                invoke(setting, "off" if original.output["enabled"] else "on")
                invoke(setting, "get")
            finally:
                invoke(setting, restore)
                invoke(setting, "get")
        else:
            before = original.output["value"]
            try:
                invoke(setting, "set", value=before - 1 if before else 1)
                invoke(setting, "get")
            finally:
                invoke(setting, "set", value=before)
                invoke(setting, "get")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
