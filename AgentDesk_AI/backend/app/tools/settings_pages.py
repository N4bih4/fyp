"""Open an allow-listed Windows Settings page, without changing settings."""
import os
import platform
from typing import Literal
from pydantic import BaseModel
from ..verification import failed_result, verdict, window_check
from .base import BaseTool, RiskLevel, ToolResult, Verification

PAGES = {
    "root": "ms-settings:", "display": "ms-settings:display",
    "sound": "ms-settings:sound", "bluetooth": "ms-settings:bluetooth",
    "wifi": "ms-settings:network-wifi", "lockscreen": "ms-settings:lockscreen",
    "windowsupdate": "ms-settings:windowsupdate",
}


class OpenWindowsSettingsArgs(BaseModel):
    page: Literal["root", "display", "sound", "bluetooth", "wifi", "lockscreen", "windowsupdate"] = "root"


class OpenWindowsSettingsTool(BaseTool):
    name = "open_windows_settings"
    description = "Open Windows Settings directly to root/display/sound/bluetooth/wifi/lockscreen/windowsupdate. Does not change settings."
    args_schema = OpenWindowsSettingsArgs
    risk_level = RiskLevel.LOW

    def execute(self, args):
        parsed = self.validate_args(args.model_dump())
        if platform.system() != "Windows":
            return ToolResult(success=False, error="Windows Settings requires Windows.")
        try:
            os.startfile(PAGES[parsed.page])
            return ToolResult(success=True, output={"page": parsed.page, "uri": PAGES[parsed.page], "launch_requested": True})
        except OSError as exc:
            return ToolResult(success=False, error=f"Windows could not launch Settings: {exc}")

    def verify(self, args, result: ToolResult) -> Verification:
        if not result.success:
            return failed_result(result)
        seen, windows = window_check(title_contains=["settings"], processes={"systemsettings.exe", "applicationframehost.exe"})
        return verdict([("Settings window is open", seen)], {"page": result.output.get("page"), **windows},
                       details="The window is confirmed; the exact sub-page is not read.")


