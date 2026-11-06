"""drive_coding_agent: prompt goes in, the screen is watched until it stops changing, the text on screen comes back."""
from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from app.tools import coding_agent as ca
from app.tools.uia_backend import UiaError, WindowRef
from app.vision.boxes import OcrLine

RECT = (0, 0, 1000, 600)


def pic(shade: int, box: bool = False) -> Image.Image:
    img = Image.new("RGB", (1000, 600), (shade, shade, shade))
    if box:
        ImageDraw.Draw(img).rectangle((300, 500, 700, 560), fill=(255, 255, 255))
    return img


class FakeScreen:
    def __init__(self, pictures):
        self.pictures = list(pictures)
        self.clicks: list[tuple[int, int]] = []

    def focus(self, window): pass
    def window_rect(self, window): return RECT
    def click(self, x, y, double=False): self.clicks.append((x, y))
    def type_text(self, text): pass
    def scroll(self, x, y, amount): pass

    def grab(self, rect):
        return self.pictures.pop(0) if len(self.pictures) > 1 else self.pictures[0]


class FakeService:
    def __init__(self, title="Antigravity", found=True):
        self.title, self.found = title, found

    def window(self, query):
        if not self.found:
            raise UiaError("not open")
        return WindowRef(self.title, "Antigravity.exe")


class FakeOcr:
    def recognize(self, image):
        return [OcrLine("Created the login page", (10, 10, 200, 30), []), OcrLine("Done", (10, 40, 60, 60), [])]


@pytest.fixture()
def machine(monkeypatch):
    log: list = []
    monkeypatch.setattr(ca, "set_clipboard", lambda t: log.append(("clip", t)))
    monkeypatch.setattr(ca, "get_clipboard", lambda: "old clipboard")
    monkeypatch.setattr(ca, "press", lambda *k: log.append(("press", k)))
    monkeypatch.setattr(ca, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(ca, "get_ocr", lambda: FakeOcr())
    monkeypatch.setattr(ca.time, "sleep", lambda s: None)
    return log


def run(monkeypatch, screen, service=None, **kw):
    monkeypatch.setattr(ca, "get_screen", lambda: screen)
    monkeypatch.setattr(ca, "get_service", lambda: service or FakeService())
    tool = ca.CodingAgentTool.__new__(ca.CodingAgentTool)
    args = ca.CodingAgentArgs(app="antigravity", prompt="make a login page", settle_seconds=3, wait_seconds=5, **kw)
    return tool.execute(args)


def test_prompt_is_pasted_sent_and_the_screen_text_comes_back(monkeypatch, machine):
    # before / after paste differ (the prompt appeared), then the picture stays the same: the agent has stopped
    screen = FakeScreen([pic(20), pic(20, box=True)])
    clock = iter(x * 1.5 for x in range(1, 200))
    monkeypatch.setattr(ca.time, "monotonic", lambda: next(clock))
    out = run(monkeypatch, screen)
    assert out.success, out.error
    assert ("clip", "make a login page") in machine and ("press", ("ctrl", "v")) in machine and ("press", ("enter",)) in machine
    assert machine[-1] == ("clip", "old clipboard")                         # the user's own clipboard is put back
    assert out.output["finished"] is True and "login page" in out.output["screen_text"]
    assert screen.clicks[0] == (580, 534)                                   # the prompt box position for Antigravity, from the window size


def test_nothing_appearing_in_the_box_is_reported_not_pretended(monkeypatch, machine):
    out = run(monkeypatch, FakeScreen([pic(20)]))                           # the picture never changes after the paste
    assert not out.success and "nothing appeared" in out.error
    assert ("press", ("enter",)) not in machine                              # Enter is never pressed into the void


def test_app_not_open_and_unknown_app(monkeypatch, machine):
    out = run(monkeypatch, FakeScreen([pic(20)]), service=FakeService(found=False))
    assert not out.success and "not open" in out.error
    monkeypatch.setattr(ca, "get_service", lambda: FakeService())
    tool = ca.CodingAgentTool.__new__(ca.CodingAgentTool)
    assert "do not know" in tool.execute(ca.CodingAgentArgs(app="notarealapp", prompt="x")).error


def test_unverified_layouts_say_so(monkeypatch, machine):
    screen = FakeScreen([pic(20), pic(20, box=True)])
    clock = iter(x * 1.5 for x in range(1, 200))
    monkeypatch.setattr(ca.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(ca, "get_screen", lambda: screen)
    monkeypatch.setattr(ca, "get_service", lambda: FakeService("Claude"))
    tool = ca.CodingAgentTool.__new__(ca.CodingAgentTool)
    out = tool.execute(ca.CodingAgentArgs(app="claude", prompt="hello", settle_seconds=3, wait_seconds=5))
    assert out.success and out.output["layout_verified"] is False and "guess" in out.output["note"]


def test_tool_is_registered_needs_approval_and_is_shown_for_coding_requests():
    from app.nlu.shortlist import tools_for
    from app.tools.registry import ToolRegistry
    reg = ToolRegistry()
    tool = reg.get("drive_coding_agent")
    assert tool.requires_approval and tool.isolation == "thread"
    assert "drive_coding_agent" in tools_for("Antigravity kholo aur ye prompt do", reg.model_names(), [], [])
