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
    "apps": "ms-settings:appsfeatures", "battery": "ms-settings:batterysaver", "privacy": "ms-settings:privacy", "network": "ms-settings:network",
    "personalization": "ms-settings:personalization", "storage": "ms-settings:storagesense", "defaultapps": "ms-settings:defaultapps",
    "startupapps": "ms-settings:startupapps", "about": "ms-settings:about", "nightlight": "ms-settings:nightlight", "notifications": "ms-settings:notifications",
    "accounts": "ms-settings:yourinfo", "datetime": "ms-settings:dateandtime", "mouse": "ms-settings:mousetouchpad", "printers": "ms-settings:printers",
    "power": "ms-settings:powersleep", "vpn": "ms-settings:network-vpn", "hotspot": "ms-settings:network-mobilehotspot", "airplane": "ms-settings:network-airplanemode",
    "language": "ms-settings:regionlanguage", "troubleshoot": "ms-settings:troubleshoot", "recovery": "ms-settings:recovery", "security": "windowsdefender:",
    # the classic Windows tools (the Control Panel and its friends): opened by the shell, never configured
    "controlpanel": "control.exe", "devicemanager": "devmgmt.msc", "networkconnections": "ncpa.cpl", "poweroptions": "powercfg.cpl",
    "programsfeatures": "appwiz.cpl", "diskmanagement": "diskmgmt.msc", "taskmanager": "taskmgr.exe", "systemproperties": "sysdm.cpl", "services": "services.msc",
}
# what the window of each page is called (the verifier looks for it); everything not listed here is a Settings window
CLASSIC_TITLES = {"controlpanel": ["control panel"], "devicemanager": ["device manager"], "networkconnections": ["network connections"],
                  "poweroptions": ["power options"], "programsfeatures": ["programs and features"], "diskmanagement": ["disk management"],
                  "taskmanager": ["task manager"], "systemproperties": ["system properties"], "services": ["services"], "security": ["windows security", "security"]}
CLASSIC_PROCESSES = {"explorer.exe", "mmc.exe", "taskmgr.exe", "systemsettings.exe", "applicationframehost.exe", "securityhealthsystray.exe", "windowsdefender.exe",
                     "mmc.exe", "rundll32.exe", "control.exe"}


class OpenWindowsSettingsArgs(BaseModel):
    page: Literal[tuple(PAGES)] = "root"          # type: ignore[valid-type]


class OpenWindowsSettingsTool(BaseTool):
    name = "open_windows_settings"
    description = ("Open a Windows Settings page (display, sound, bluetooth, wifi, apps, battery, privacy, network, storage, default apps, startup apps, about, ...) "
                   "or a classic tool (Control Panel, Device Manager, Network Connections, Power Options, Programs and Features, Disk Management, Task Manager). "
                   "Does not change anything.")
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
        titles = CLASSIC_TITLES.get(result.output.get("page"), ["settings"])
        seen, windows = window_check(title_contains=titles, processes=CLASSIC_PROCESSES, match="any") if result.output.get("page") in CLASSIC_TITLES else             window_check(title_contains=["settings"], processes={"systemsettings.exe", "applicationframehost.exe"})
        return verdict([("Settings window is open", seen)], {"page": result.output.get("page"), **windows},
                       details="The window is confirmed; the exact sub-page is not read.")


