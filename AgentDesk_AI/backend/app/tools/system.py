"""Windows system controls and screenshots."""
from __future__ import annotations

import asyncio
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..security.paths import resolve_within_allowed
from ..runtime import data_root, system_worker_command
from ..verification import ProbeUnavailable, current, failed_result, file_evidence, verdict
from .base import BaseTool, RiskLevel, ToolContext, ToolResult, Verification


class ManageSystemSettingArgs(BaseModel):
    setting: Literal["brightness", "volume", "bluetooth", "wifi", "theme"]
    action: Literal["get", "set", "increase", "decrease", "mute", "unmute", "on", "off", "dark", "light"]
    value: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_setting_action(self):
        supported_actions = {
            "brightness": {"get", "set", "increase", "decrease"},
            "volume": {"get", "set", "increase", "decrease", "mute", "unmute"},
            "bluetooth": {"get", "on", "off"},
            "wifi": {"get", "on", "off"},
            "theme": {"get", "dark", "light"},
        }
        if self.action not in supported_actions[self.setting]:
            raise ValueError(f"{self.action!r} is not supported for {self.setting}")
        if self.action == "set" and self.value is None:
            raise ValueError("value is required for set and must be between 0 and 100")
        if self.action in {"increase", "decrease"}:
            if self.value is None:
                self.value = 10
            elif self.value == 0:
                raise ValueError("value for increase/decrease must be between 1 and 100")
        elif self.action not in {"set"} and self.value is not None:
            raise ValueError(f"value is not used for {self.action}")
        return self


class ManageSystemSettingTool(BaseTool):
    name = "manage_system_setting"
    description = (
        "Read or change Windows display brightness, master volume, or Bluetooth/Wi-Fi. "
        "Use setting=brightness or volume with get/set/increase/decrease (value is a percentage; "
        "increase/decrease default to 10), or setting=volume with mute/unmute. "
        "Use setting=bluetooth or wifi with get/on/off; setting=theme with get/dark/light changes Windows and apps theme. Only use for the user's direct request."
    )
    risk_level = RiskLevel.MEDIUM
    args_schema = ManageSystemSettingArgs

    def risk_for_args(self, args: BaseModel | None) -> RiskLevel:
        if args is not None and (ManageSystemSettingArgs.model_validate(args.model_dump()).action == "get" or args.setting in {"brightness", "volume", "theme"}):
            return RiskLevel.LOW
        return RiskLevel.MEDIUM

    @staticmethod
    def _require_windows() -> None:
        if platform.system() != "Windows":
            raise RuntimeError("System brightness, volume, and Bluetooth controls are supported on Windows only.")

    @staticmethod
    def _brightness() -> int:
        try:
            import screen_brightness_control as sbc
        except ImportError as exc:
            raise RuntimeError(
                "Brightness support is not installed. Install backend requirements and restart."
            ) from exc
        values = sbc.get_brightness(display=0)
        if not values:
            raise RuntimeError("Windows did not report a controllable display brightness level.")
        return int(round(float(values[0])))

    @staticmethod
    def _set_brightness(value: int) -> None:
        try:
            import screen_brightness_control as sbc
        except ImportError as exc:
            raise RuntimeError(
                "Brightness support is not installed. Install backend requirements and restart."
            ) from exc
        sbc.set_brightness(value, display=0)

    @staticmethod
    def _volume_endpoint():
        try:
            from pycaw.pycaw import AudioUtilities
        except ImportError as exc:
            raise RuntimeError(
                "Volume support is not installed. Install backend requirements and restart."
            ) from exc
        speakers = AudioUtilities.GetSpeakers()
        if speakers is None:
            raise RuntimeError("Windows did not report a default audio output device.")
        return speakers.EndpointVolume

    @classmethod
    def _volume(cls) -> int:
        return int(round(cls._volume_endpoint().GetMasterVolumeLevelScalar() * 100))

    @classmethod
    def _set_volume(cls, value: int) -> None:
        cls._volume_endpoint().SetMasterVolumeLevelScalar(value / 100, None)

    @classmethod
    def _set_mute(cls, muted: bool) -> None:
        endpoint = cls._volume_endpoint()
        endpoint.SetMute(1 if muted else 0, None)
        if bool(endpoint.GetMute()) != muted:
            raise RuntimeError("Windows did not apply the requested mute state.")

    @staticmethod
    def _theme() -> dict:
        import winreg
        path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            values = {}
            for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
                try:
                    values[name] = winreg.QueryValueEx(key, name)[0]
                except FileNotFoundError:
                    values[name] = 1
        return {"apps": "light" if values["AppsUseLightTheme"] else "dark",
                "system": "light" if values["SystemUsesLightTheme"] else "dark"}

    @classmethod
    def _set_theme(cls, mode: str) -> dict:
        import ctypes
        import winreg
        path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        before = cls._theme()
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            try:
                for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
                    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(mode == "light"))
            except OSError:
                winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, int(before["apps"] == "light"))
                winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, int(before["system"] == "light"))
                raise
        # Notify interested apps; some applications keep their own theme preference.
        from ctypes import wintypes
        notify = ctypes.windll.user32.SendMessageTimeoutW
        notify.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR,
                           wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        notify.restype = wintypes.LPARAM
        result = ctypes.c_size_t()
        notify(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x0002, 1000, ctypes.byref(result))
        actual = cls._theme()
        if actual != {"apps": mode, "system": mode}:
            raise RuntimeError("Windows theme values did not match the requested mode.")
        return actual

    @staticmethod
    async def _get_radio(kind):
        try:
            from winsdk.windows.devices.radios import Radio, RadioKind
        except ImportError as exc:
            raise RuntimeError("Radio support is not installed in the backend runtime.") from exc
        radios = await Radio.get_radios_async()
        expected = RadioKind.BLUETOOTH if kind == "bluetooth" else RadioKind.WI_FI
        matches = [radio for radio in radios if radio.kind == expected]
        if not matches:
            raise RuntimeError(f"Windows did not find a {kind} radio.")
        if len(matches) > 1:
            raise RuntimeError(f"Multiple {kind} radios found; select the adapter in Windows Settings.")
        return matches[0]

    @classmethod
    def _radio_state(cls, kind):
        async def read():
            from winsdk.windows.devices.radios import RadioState
            radio = await cls._get_radio(kind)
            if radio.state not in (RadioState.ON, RadioState.OFF):
                raise RuntimeError(f"{kind} radio is disabled or unavailable ({radio.state}); check hardware switch or Windows policy.")
            return radio.state == RadioState.ON
        return asyncio.run(asyncio.wait_for(read(), timeout=8))

    @classmethod
    def _set_radio(cls, kind, enabled):
        async def change():
            from winsdk.windows.devices.radios import Radio, RadioAccessStatus, RadioState
            radio = await cls._get_radio(kind)
            target = RadioState.ON if enabled else RadioState.OFF
            if radio.state == target:
                return
            access = await Radio.request_access_async()
            if access != RadioAccessStatus.ALLOWED:
                raise RuntimeError(f"Windows denied {kind} access ({access}); check Windows permissions/policy.")
            result = await radio.set_state_async(target)
            if result != RadioAccessStatus.ALLOWED:
                raise RuntimeError(f"Windows rejected {kind} change ({result}).")
            for _ in range(25):
                if radio.state == target:
                    return
                await asyncio.sleep(0.1)
            raise RuntimeError(f"Windows did not apply {kind} state; check hardware switch or policy.")
        asyncio.run(asyncio.wait_for(change(), timeout=12))

    @classmethod
    def _bluetooth(cls):
        return cls._radio_state("bluetooth")

    @classmethod
    def _set_bluetooth(cls, enabled):
        cls._set_radio("bluetooth", enabled)

    def execute(self, args: BaseModel) -> ToolResult:
        parsed = ManageSystemSettingArgs.model_validate(args.model_dump())
        if platform.system() == "Windows" and self.ctx.isolate_system_controls and parsed.setting in {"volume", "brightness", "bluetooth", "wifi"}:
            # COM/WMI objects cannot safely be shared across short-lived executor
            # threads. Native library faults must not crash the API process.
            try:
                child = subprocess.run(
                    system_worker_command(),
                    input=parsed.model_dump_json(), text=True, capture_output=True,
                    encoding="utf-8", errors="replace", timeout=20, shell=False,
                    cwd=str(data_root()),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for line in reversed(child.stdout.splitlines()):
                    if line.startswith("AGENTX_RESULT=") and child.returncode == 0:
                        return ToolResult.model_validate_json(line.removeprefix("AGENTX_RESULT="))
                return ToolResult(success=False, error=f"Windows {parsed.setting} worker stopped (code {child.returncode}). Backend remains available.")
            except subprocess.TimeoutExpired:
                return ToolResult(success=False, error=f"Windows {parsed.setting} did not respond within 20 seconds; worker was stopped.")
            except (OSError, ValueError) as exc:
                return ToolResult(success=False, error=f"Could not run Windows setting worker: {exc}")
        return self._execute(parsed)

    def _execute(self, args: BaseModel) -> ToolResult:
        try:
            parsed = ManageSystemSettingArgs.model_validate(args.model_dump())
            self._require_windows()
            if parsed.setting == "theme":
                state = self._theme() if parsed.action == "get" else self._set_theme(parsed.action)
                return ToolResult(success=True, output={"setting": "theme", **state})
            if parsed.setting == "brightness":
                current = self._brightness()
                if parsed.action == "get":
                    return ToolResult(success=True, output={"setting": "brightness", "value": current})
                if parsed.action == "set":
                    value = parsed.value
                else:
                    amount = parsed.value if parsed.value is not None else 10
                    value = current + (amount if parsed.action == "increase" else -amount)
                if value is None:
                    raise RuntimeError("A percentage value is required to set brightness.")
                value = max(0, min(100, value))
                self._set_brightness(value)
                actual = self._brightness()
                if abs(actual - value) > 2:
                    raise RuntimeError(f"Brightness requested {value}%, but display reports {actual}%.")
                return ToolResult(success=True, output={"setting": "brightness", "value": actual})
            if parsed.setting == "volume":
                if parsed.action == "get":
                    muted = bool(self._volume_endpoint().GetMute())
                    return ToolResult(success=True, output={"setting": "volume", "value": self._volume(), "muted": muted})
                if parsed.action == "mute":
                    self._set_mute(True)
                    return ToolResult(success=True, output={"setting": "volume", "muted": True})
                if parsed.action == "unmute":
                    self._set_mute(False)
                    return ToolResult(success=True, output={"setting": "volume", "muted": False})
                current = self._volume()
                if parsed.action == "set":
                    value = parsed.value
                else:
                    amount = parsed.value if parsed.value is not None else 10
                    value = current + (amount if parsed.action == "increase" else -amount)
                if value is None:
                    raise RuntimeError("A percentage value is required to set volume.")
                value = max(0, min(100, value))
                self._set_volume(value)
                if parsed.action == "increase" or (parsed.action == "set" and value > 0):
                    self._set_mute(False)
                actual = self._volume()
                if abs(actual - value) > 1:
                    raise RuntimeError(f"Volume requested {value}%, but device reports {actual}%.")
                return ToolResult(success=True, output={"setting": "volume", "value": actual})
            if parsed.action == "get":
                state = self._bluetooth() if parsed.setting == "bluetooth" else self._radio_state("wifi")
                return ToolResult(success=True, output={"setting": parsed.setting, "enabled": state})
            enabled = parsed.action == "on"
            if parsed.setting == "bluetooth":
                self._set_bluetooth(enabled)
            else:
                self._set_radio("wifi", enabled)
            return ToolResult(success=True, output={"setting": parsed.setting, "enabled": enabled})
        except TimeoutError:
            return ToolResult(success=False, error="Windows radio operation timed out; state was not confirmed.")
        except Exception as exc:
            return ToolResult(success=False, error=f"Could not manage system setting: {exc}")

    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        """Re-read the setting in a separate process and compare with what was asked."""
        if not result.success:
            return failed_result(result)
        parsed = ManageSystemSettingArgs.model_validate(args.model_dump())
        reported = result.output or {}
        try:
            observed = current().read_setting(parsed.setting)
        except ProbeUnavailable as exc:
            return Verification(passed=False, checks=["independent read-back unavailable"], details=str(exc))
        except Exception as exc:  # noqa: BLE001 - a failed read is not a pass
            return Verification(passed=False, checks=["independent read-back failed"], details=str(exc)[:200])
        evidence = {"reported": reported, "observed": observed}
        if parsed.setting == "theme":
            want = parsed.action if parsed.action in {"dark", "light"} else reported.get("system")
            return verdict([("registry theme matches", observed.get("system") == want and observed.get("apps") == want)], evidence)
        if parsed.setting in {"bluetooth", "wifi"}:
            want = {"on": True, "off": False}.get(parsed.action, reported.get("enabled"))
            return verdict([(f"{parsed.setting} state read back", observed.get("enabled") is want)], evidence)
        if parsed.action in {"mute", "unmute"}:
            return verdict([("mute state read back", observed.get("muted") is (parsed.action == "mute"))], evidence)
        tolerance = 1 if parsed.setting == "volume" else 2
        value = observed.get("value")
        checks = [("value read back matches report", isinstance(value, int) and abs(value - int(reported.get("value", -99))) <= tolerance)]
        if parsed.action == "set":
            checks.append(("value equals requested", isinstance(value, int) and abs(value - parsed.value) <= tolerance))
        return verdict(checks, evidence)


class TakeScreenshotArgs(BaseModel):
    output_path: str | None = Field(
        default=None, description="Absolute path for the PNG (default: test dir / screenshots)"
    )


class TakeScreenshotTool(BaseTool):
    name = "take_screenshot"
    description = (
        "Capture the current screen to a PNG file inside an allowed directory. "
        "Medium risk: the image may contain private on-screen content."
    )
    risk_level = RiskLevel.MEDIUM
    args_schema = TakeScreenshotArgs

    def _default_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.ctx.test_dir / "screenshots" / f"screenshot_{stamp}.png"

    def execute(self, args: BaseModel) -> ToolResult:
        a = TakeScreenshotArgs.model_validate(args.model_dump())
        try:
            dest = resolve_within_allowed(
                a.output_path or str(self._default_path()), self.ctx.allowed_directories
            )
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        if dest.suffix.lower() != ".png":
            dest = dest.with_suffix(".png")
        try:
            from PIL import ImageGrab  # Pillow; works on Windows/macOS
        except ImportError:
            return ToolResult(success=False, error="Pillow is not installed; cannot take screenshots")
        try:
            img = ImageGrab.grab()
        except Exception as exc:  # noqa: BLE001 - e.g. headless Linux
            return ToolResult(
                success=False,
                error=f"Screenshots are not available in this environment: {exc}",
            )
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            img.save(dest)
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not save screenshot: {exc}")
        return ToolResult(success=True, output={"path": str(dest)})

    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        if not result.success:
            return failed_result(result)
        p = Path(result.output["path"])
        header = p.read_bytes()[:8] if p.is_file() else b""
        return verdict([("PNG file exists and is non-empty", p.is_file() and p.stat().st_size > 0),
                        ("file has a PNG header", header == b"\x89PNG\r\n\x1a\n")], file_evidence(p))

def system_tools(ctx: ToolContext | None = None) -> list[BaseTool]:
    ctx = ctx or ToolContext.from_settings()
    from .settings_pages import OpenWindowsSettingsTool
    return [ManageSystemSettingTool(ctx), TakeScreenshotTool(ctx), OpenWindowsSettingsTool(ctx)]


