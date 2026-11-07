"""drive_coding_agent: prompt goes in, the screen is watched until it stops changing, the text on screen comes back."""
from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from app.tools import coding_agent as ca
from app.tools.uia_backend import UiaError, WindowRef
from app.vision.ocr import OcrUnavailable
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
    monkeypatch.setattr(ca, "USE_PRINTWINDOW", False)
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
    monkeypatch.setattr(ca, "get_service", lambda: FakeService("Cursor"))
    tool = ca.CodingAgentTool.__new__(ca.CodingAgentTool)
    out = tool.execute(ca.CodingAgentArgs(app="cursor", prompt="hello", settle_seconds=3, wait_seconds=5))
    assert out.success and out.output["layout_verified"] is False and "guess" in out.output["note"]


def test_tool_is_registered_needs_approval_and_is_shown_for_coding_requests():
    from app.nlu.shortlist import tools_for
    from app.tools.registry import ToolRegistry
    reg = ToolRegistry()
    tool = reg.get("drive_coding_agent")
    assert tool.requires_approval and tool.isolation == "thread"
    assert "drive_coding_agent" in tools_for("Antigravity kholo aur ye prompt do", reg.model_names(), [], [])


def test_a_renamed_window_is_still_the_same_app(monkeypatch, machine):
    """Antigravity renames its window to the conversation's title after the first reply: the watcher must not think it went behind another window."""
    class Renaming(FakeService):
        def window(self, query):
            return WindowRef("Antigravity" if query else "Ignoring System Instructions", "Antigravity.exe", handle=0)

    screen = FakeScreen([pic(20), pic(20, box=True)])
    clock = iter(x * 1.5 for x in range(1, 200))
    monkeypatch.setattr(ca.time, "monotonic", lambda: next(clock))
    out = run(monkeypatch, screen, service=Renaming())
    assert out.success and out.output["finished"] is True


class LinesOcr:
    def __init__(self, lines):
        self.lines = lines

    def recognize(self, image):
        return [OcrLine(text, rect, []) for text, rect in self.lines]


def test_prompt_box_is_found_by_its_placeholder_text(monkeypatch):
    img = pic(20)                                                   # 1000 x 600
    monkeypatch.setattr(ca, "get_ocr", lambda: LinesOcr([
        ("Ask anything about your code", (100, 100, 400, 120)),     # quoted high up in the chat: must be ignored
        ("Ask anything, @ to mention, / for actions", (300, 540, 700, 560)),
        ("Settings", (10, 580, 80, 596))]))
    x, y = ca.find_prompt_box(img, ["ask anything"])
    assert (round(x, 2), round(y, 2)) == (0.5, 0.92)


def test_no_match_or_no_ocr_means_the_measured_place_is_used(monkeypatch):
    img = pic(20)
    monkeypatch.setattr(ca, "get_ocr", lambda: LinesOcr([("Something else", (300, 540, 700, 560))]))
    assert ca.find_prompt_box(img, ["ask anything"]) is None

    def broken():
        raise OcrUnavailable("no language")
    monkeypatch.setattr(ca, "get_ocr", broken)
    assert ca.find_prompt_box(img, ["ask anything"]) is None


def test_the_click_goes_where_the_placeholder_is(monkeypatch, machine):
    screen = FakeScreen([pic(20), pic(20, box=True)])
    clock = iter(x * 1.5 for x in range(1, 200))
    monkeypatch.setattr(ca.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(ca, "get_ocr", lambda: LinesOcr([("Ask anything", (300, 540, 700, 560))]))
    out = run(monkeypatch, screen)
    assert out.success and out.output["prompt_box_found_by"] == "ocr" and screen.clicks[0] == (500, 550)


def test_claude_and_antigravity_are_measured_profiles_the_rest_are_marked_guesses():
    assert ca.PROFILES["antigravity"]["verified"] and ca.PROFILES["claude"]["verified"]
    assert not any(ca.PROFILES[k]["verified"] for k in ("codex", "cursor", "chatgpt"))
    assert all(ca.PROFILES[k]["hints"] for k in ca.PROFILES)
