import subprocess

from app.tools import packages
from app.tools.base import RiskLevel, ToolContext

TABLE = ("Name" + " " * 20 + "Id" + " " * 20 + "Version  Source\n" + "-" * 60 + "\n"
         + "VLC media player".ljust(24) + "VideoLAN.VLC".ljust(22) + "3.0.20   winget\n"
         + "VLC Remote".ljust(24) + "Other.VLCRemote".ljust(22) + "1.0      winget\n"
         + "Git".ljust(24) + "Git.Git".ljust(22) + "2.45     winget\n")


def fake(monkeypatch, listing, calls, uninstall_code=0, still_there=False):
    def run(args, timeout):
        calls.append(args)
        if args[0] == "list" and "--exact" in args:
            return subprocess.CompletedProcess(args, 0 if still_there else 1, args[args.index("--id") + 1] if still_there else "", "")
        if args[0] == "list":
            return subprocess.CompletedProcess(args, 0, listing, "")
        return subprocess.CompletedProcess(args, uninstall_code, "Successfully uninstalled", "")
    monkeypatch.setattr(packages, "run_winget", run)


def test_the_table_is_parsed():
    assert packages.parse_winget_list(TABLE) == [("VLC media player", "VideoLAN.VLC"), ("VLC Remote", "Other.VLCRemote"), ("Git", "Git.Git")]


def test_uninstall_is_high_risk():
    assert packages.WingetUninstallTool(ToolContext()).risk_level == RiskLevel.HIGH


def test_one_clear_match_is_uninstalled_and_checked(monkeypatch):
    calls = []
    fake(monkeypatch, TABLE, calls)
    tool = packages.WingetUninstallTool(ToolContext())
    args = tool.validate_args({"app": "git"})
    result = tool.execute(args)
    assert result.success and result.output["package_id"] == "Git.Git"
    assert any(c[0] == "uninstall" and "Git.Git" in c and "--exact" in c for c in calls)
    assert tool.verify(args, result).passed                          # winget list no longer shows it


def test_a_name_that_fits_two_apps_uninstalls_nothing(monkeypatch):
    calls = []
    fake(monkeypatch, TABLE, calls)
    tool = packages.WingetUninstallTool(ToolContext())
    result = tool.execute(tool.validate_args({"app": "vlc"}))
    assert not result.success and result.output["needs_confirmation"] and len(result.output["candidates"]) == 2
    assert not any(c[0] == "uninstall" for c in calls)


def test_an_unknown_app_and_a_failed_uninstall_are_reported(monkeypatch):
    calls = []
    fake(monkeypatch, TABLE, calls)
    tool = packages.WingetUninstallTool(ToolContext())
    assert not tool.execute(tool.validate_args({"app": "nothing here"})).success
    fake(monkeypatch, TABLE, calls, uninstall_code=1)
    assert not tool.execute(tool.validate_args({"app": "git"})).success
    fake(monkeypatch, TABLE, calls, still_there=True)
    args = tool.validate_args({"app": "git"})
    assert not tool.verify(args, tool.execute(args)).passed           # winget still lists it: not verified
