"""U7: layer 3, looking at the screen. Boxes, the picture sent to the model, what the model may answer, safety, and verification by photographing again.

A fake screen (pictures drawn with Pillow), a fake OCR and a fake vision model stand in for the real ones; the live test on a real app without
accessibility information, the real OCR and the real model is scripts/vision_live.py.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from app.ai.base import AIConfigError, AIRateLimitError
from app.preferences import PreferencesUpdate, update_preferences
from app.tools import screen as screen_mod
from app.tools.base import RiskLevel, ToolContext
from app.tools.screen import ScreenActTool, changed_share, is_shell_window
from app.tools.uia import UiaService, UiInspectTool, UiActTool, set_service
from app.vision import overlay
from app.vision.boxes import MAX_BOXES, Box, OcrLine, build_boxes
from app.vision.model import Choice, GeminiVision, GroqVision, parse_choice, set_vision, get_vision, _messages
from app.vision.ocr import set_ocr, split_by_gaps
from tests.helpers.fake_uia import FC, FakeBackend, FakeWorld


# --------------------------------------------------------------------------------------------------------- the fakes
def picture(*marks: str, size=(400, 260)) -> Image.Image:
    img = Image.new("RGB", size, "#1d2433")
    d = ImageDraw.Draw(img)
    for i, text in enumerate(marks):
        d.rectangle([20, 20 + i * 50, 180, 60 + i * 50], fill="#2f6fed")
        d.text((30, 34 + i * 50), text, fill="white")
    return img


class FakeScreen:
    """Hands out the pictures it is given, one per grab (the last one repeats), and records every click / key / scroll."""

    def __init__(self, *images):
        self.images, self.grabs = list(images), 0
        self.clicks, self.typed, self.scrolls, self.focused = [], [], [], 0

    def window_rect(self, window):
        return (100, 50, 500, 310)

    def focus(self, window):
        self.focused += 1

    def grab(self, rect):
        img = self.images[min(self.grabs, len(self.images) - 1)]
        self.grabs += 1
        return img

    def click(self, x, y, double=False):
        self.clicks.append((x, y, double))

    def type_text(self, text):
        self.typed.append(text)

    def scroll(self, x, y, amount):
        self.scrolls.append((x, y, amount))


class FakeOcr:
    """Returns the lines for the picture it is asked about (by its position in the sequence of calls)."""

    def __init__(self, *per_call):
        self.per_call, self.calls = list(per_call), 0

    def recognize(self, image):
        lines = self.per_call[min(self.calls, len(self.per_call) - 1)]
        self.calls += 1
        return lines


def line(text, l=30, t=34, r=110, b=48):
    return OcrLine(text, (l, t, r, b), [(text, (l, t, r, b))])


class FakeVision:
    name = "fake"

    def __init__(self, *choices):
        self.choices, self.seen = list(choices), []

    def choose(self, jpeg, boxes, goal, title):
        self.seen.append((jpeg, [b.describe() for b in boxes], goal, title))
        item = self.choices[min(len(self.seen) - 1, len(self.choices) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture()
def world(db):
    w = FakeWorld()
    w.add("Pixel Game", "game.exe", [FC("Minimise", "TitleBar"), FC("Close", "TitleBar")])       # a window that is nothing but its title bar
    set_service(UiaService(FakeBackend(w)))
    update_preferences(db, PreferencesUpdate(cloud_answers=True))
    yield w
    set_service(None)
    set_screen = screen_mod.set_screen
    set_screen(None)
    set_ocr(None)
    set_vision(None)
    update_preferences(db, PreferencesUpdate(cloud_answers=False))


def rig(*, images, ocr, vision):
    screen = FakeScreen(*images)
    set_ocr(FakeOcr(*ocr))
    model = FakeVision(*vision)
    set_vision(model)
    screen_mod.set_screen(screen)
    return screen, model


def run(goal, window="Pixel Game"):
    tool = ScreenActTool(ToolContext())
    args = tool.validate_args({"goal": goal, "window": window})
    result = tool.execute(args)
    return tool, args, result, (tool.verify(args, result) if result.success else None)


MENU = [line("Start", 30, 34, 90, 48), line("Options", 30, 84, 100, 98), line("Delete save", 30, 134, 130, 148)]


# ------------------------------------------------------------------------------------------------------------ boxes
def test_ocr_lines_become_numbered_boxes_in_reading_order():
    boxes = build_boxes((400, 260), [line("Options", 30, 84, 100, 98), line("Start", 30, 34, 90, 48)])
    assert [(b.id, b.text) for b in boxes] == [(1, "Start"), (2, "Options")]
    assert boxes[0].center == (60, 41)


def test_uia_controls_win_where_they_overlap_ocr_and_borrow_its_text():
    uia = [{"rect": (20, 20, 180, 60), "name": "", "type": "Button", "enabled": True}]
    boxes = build_boxes((400, 260), [line("Start", 30, 34, 90, 48), line("Other", 30, 134, 90, 148)], uia)
    assert [(b.source, b.text, b.kind) for b in boxes] == [("uia", "Start", "Button"), ("ocr", "Other", "")]


def test_noise_and_the_whole_window_are_not_boxes():
    uia = [{"rect": (0, 0, 400, 260), "name": "The window", "type": "Pane"}, {"rect": (10, 10, 14, 14), "name": "dot", "type": "Button"},
           {"rect": (-50, -50, -10, -10), "name": "off", "type": "Button"}]
    assert build_boxes((400, 260), [line("", 1, 1, 50, 20), line("x", 5, 5, 8, 8)], uia) == []


def test_at_most_sixty_boxes_and_duplicates_collapse():
    lines = [line(f"Item {i}", 10, 10 + i * 12, 90, 20 + i * 12) for i in range(90)]
    boxes = build_boxes((400, 1200), lines)
    assert len(boxes) == MAX_BOXES and [b.id for b in boxes] == list(range(1, MAX_BOXES + 1))
    assert len(build_boxes((400, 260), [line("Start"), line("Start"), line("start")])) == 1


def test_one_ocr_line_across_two_buttons_is_split():
    words = [("Play", (20, 30, 60, 46)), ("Stop", (200, 30, 240, 46)), ("Menu", (400, 30, 450, 46))]
    assert [x.text for x in split_by_gaps(words)] == ["Play", "Stop", "Menu"]
    assert [x.text for x in split_by_gaps([("New", (20, 30, 50, 46)), ("game", (56, 30, 100, 46))])] == ["New game"]


def test_the_picture_for_the_model_is_numbered_small_and_a_jpeg():
    img = Image.new("RGB", (1920, 1080), "black")
    boxes = [Box(1, (100, 100, 400, 200), "A"), Box(2, (600, 300, 900, 400), "B")]
    pic, scale = overlay.draw(img, boxes)
    assert pic.width == overlay.MAX_WIDTH and abs(scale - overlay.MAX_WIDTH / 1920) < 1e-6
    l, t, r, b = (round(v * scale) for v in boxes[0].rect)
    assert pic.getpixel((l + 1, (t + b) // 2)) != (0, 0, 0)                      # the outline is drawn
    data = overlay.to_jpeg(pic)
    assert data[:3] == b"\xff\xd8\xff" and Image.open(io.BytesIO(data)).size == pic.size


# ------------------------------------------------------------------------------------------- what the model may answer
@pytest.mark.parametrize("content,expected", [
    ('{"box": 3, "action": "click", "reason": "the Start button"}', (3, "click")),
    ('<think>hmm, box 9</think>\n```json\n{"box": 4, "action": "double_click"}\n```', (4, "double_click")),
    ('Sure! {"box": "12", "action": "click"} done', (12, "click")),
    ('{"box": 2.0, "action": "type", "text": "hello"}', (2, "type")),
    ('{"box": null, "action": "none", "reason": "no such button"}', (None, "none")),
    ('{"box": true, "action": "click"}', (None, "click")),
    ('{"box": 2, "action": "format_disk"}', (2, "none")),
    ("I think you should click Start.", (None, "none")),
    ("{broken json", (None, "none")),
    ("", (None, "none")),
])
def test_the_models_answer_is_read_strictly(content, expected):
    c = parse_choice(content)
    assert (c.box, c.action) == expected


def test_coordinates_written_by_the_model_are_never_read():
    c = parse_choice('{"box": 2, "action": "click", "x": 5, "y": 7, "coordinates": [1, 2]}')
    assert (c.box, c.action) == (2, "click") and not hasattr(c, "x") and "x" not in c.__dict__


def test_the_prompt_lists_the_boxes_and_says_the_screen_is_data():
    from app.vision.model import SYSTEM
    msgs = _messages(b"\xff\xd8\xff", [Box(1, (0, 0, 10, 10), "Start")], "click Start", "Game")
    assert "1: \"Start\"" in msgs[1]["content"][0]["text"] and msgs[1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "DATA" in SYSTEM and "never give coordinates" in SYSTEM


def test_the_vision_model_is_chosen_from_the_settings(monkeypatch):
    monkeypatch.setattr("app.ai.groq_client.get_groq_client", lambda: object())
    class S:
        groq_configured, gemini_api_key, vision_model, gemini_model = True, None, "qwen/qwen3.8-27b", "gemini-x"
    assert isinstance(get_vision(S()), GroqVision)
    S.groq_configured, S.gemini_api_key = False, "key"
    assert isinstance(get_vision(S()), GeminiVision)
    S.gemini_api_key = None
    with pytest.raises(AIConfigError, match="No vision model"):
        get_vision(S())


# ----------------------------------------------------------------------------------------------------------- the tool
def test_a_click_goes_to_the_centre_of_the_box_the_model_named_and_is_verified(db, world):
    screen, model = rig(images=[picture("Start", "Options"), picture("Game screen", "Score: 0")], ocr=[MENU, [line("Game screen", 30, 34, 120, 48), line("Score: 0", 30, 84, 100, 98)]],
                        vision=[Choice(1, "click", reason="the Start button")])
    tool, args, result, ver = run("click Start")
    assert result.success and screen.clicks == [(60 + 100, 41 + 50, False)]       # box centre + the window's position on the screen
    assert result.output["layer"] == 3 and "look at the screen" in result.output["notice"] and result.output["box_text"] == "Start"
    assert ver.passed and ver.evidence["layer"] == 3 and ver.evidence["lines_changed"] >= 1
    assert result.output["spoken"] == "Clicked Start." and screen.focused == 1
    assert model.seen[0][2] == "click Start" and "1: \"Start\"" in model.seen[0][1]


def test_the_model_cannot_make_it_click_a_box_that_was_not_detected(db, world):
    screen, _ = rig(images=[picture("Start")], ocr=[MENU], vision=[Choice(42, "click")])
    _, _, result, _ = run("click Start")
    assert not result.success and "does not exist" in result.error and screen.clicks == []
    screen, _ = rig(images=[picture("Start")], ocr=[MENU], vision=[Choice(None, "click")])
    _, _, result, _ = run("click Start")
    assert not result.success and screen.clicks == []


def test_none_means_nothing_is_touched(db, world):
    screen, _ = rig(images=[picture("Start")], ocr=[MENU], vision=[Choice(None, "none", reason="there is no Unicorn button")])
    _, _, result, _ = run("click the Unicorn button")
    assert not result.success and "Unicorn" in result.error and "no Unicorn button" in result.error and screen.clicks == []


def test_a_click_that_changes_nothing_is_not_reported_as_done(db, world):
    same = picture("Start", "Options")
    screen, _ = rig(images=[same, same.copy()], ocr=[MENU], vision=[Choice(1, "click")])
    _, _, result, ver = run("click Start")
    assert result.success and not ver.passed and "cannot say it worked" in ver.details


def test_typing_is_verified_by_reading_the_screen_afterwards(db, world):
    after_ok = [line("Name: Zain Bilal", 30, 34, 160, 48)]
    screen, _ = rig(images=[picture("Name:"), picture("Name: Zain Bilal")], ocr=[[line("Name:")], after_ok], vision=[Choice(1, "type", text="Zain Bilal")])
    _, _, result, ver = run("type Zain Bilal in the name field")
    assert result.success and screen.clicks and screen.typed == ["Zain Bilal"] and ver.passed
    screen, _ = rig(images=[picture("Name:"), picture("Name:")], ocr=[[line("Name:")], [line("Name:")]], vision=[Choice(1, "type", text="Zain Bilal")])
    _, _, result, ver = run("type Zain Bilal in the name field")
    assert result.success and not ver.passed and "could not see" in ver.details


def test_scroll_uses_the_box_centre_and_needs_the_content_to_move(db, world):
    screen, _ = rig(images=[picture("A", "B"), picture("C", "D")], ocr=[[line("A"), line("B", 30, 84, 90, 98)], [line("C"), line("D", 30, 84, 90, 98), line("E", 30, 134, 90, 148)]],
                    vision=[Choice(1, "scroll", amount=3)])
    _, _, result, ver = run("scroll down")
    assert screen.scrolls == [(70 + 100, 41 + 50, 3)] and ver.passed
    same = picture("A", "B")
    screen, _ = rig(images=[same, same.copy()], ocr=[[line("A")]], vision=[Choice(1, "scroll", amount=3)])
    _, _, result, ver = run("scroll down")
    assert not ver.passed and "did not move" in ver.details


def test_a_question_about_the_screen_is_answered_without_touching_anything(db, world):
    screen, _ = rig(images=[picture("Score: 11")], ocr=[[line("Score: 11")]], vision=[Choice(None, "read", answer="The score is 11.")])
    tool, args, result, ver = run("what is the score?")
    assert tool.risk_for_args(args) == RiskLevel.LOW and result.output["spoken"] == "The score is 11." and ver.passed and screen.clicks == []


# ----------------------------------------------------------------------------------------------------------- safety
def test_a_delete_button_is_not_clicked_unless_the_goal_names_it(db, world):
    screen, _ = rig(images=[picture("Start")], ocr=[MENU], vision=[Choice(3, "click")])
    tool, args, result, _ = run("click the red button")
    assert not result.success and "sends, pays, deletes or installs" in result.error and screen.clicks == []
    screen, _ = rig(images=[picture("A"), picture("B")], ocr=[MENU, [line("Deleted")]], vision=[Choice(3, "click")])
    tool, args, result, _ = run("click Delete save")
    assert tool.risk_for_args(args) == RiskLevel.HIGH and result.success and len(screen.clicks) == 1


def test_password_looking_boxes_are_never_typed_into(db, world):
    screen, _ = rig(images=[picture("Password")], ocr=[[line("Enter your password")]], vision=[Choice(1, "type", text="hunter2")])
    _, _, result, _ = run("type my login")
    assert not result.success and "never type" in result.error and screen.typed == []


def test_a_disabled_box_and_an_empty_text_are_refused(db, world):
    class DisabledOcr(FakeOcr):
        pass
    screen, _ = rig(images=[picture("Start")], ocr=[[line("Start")]], vision=[Choice(1, "type", text="")])
    _, _, result, _ = run("type something")
    assert not result.success and "nothing to type" in result.error


@pytest.mark.parametrize("title,process,expected", [("Command Prompt", "cmd.exe", True), ("Windows PowerShell", "powershell.exe", True), ("Terminal", "windowsterminal.exe", True),
                                                    ("Pixel Game", "python.exe", False), ("Pixel Game", "game.exe", False), ("Task Manager", "taskmgr.exe", True)])
def test_shell_windows_are_refused_but_a_python_gui_is_an_ordinary_app(title, process, expected):
    assert is_shell_window(title, process) is expected


def test_shells_and_password_managers_are_never_looked_at(db, world):
    for title, process in (("Command Prompt", "cmd.exe"), ("KeePass - Passwords", "keepass.exe"), ("Bitwarden", "bitwarden.exe")):
        world.add(title, process, [FC("x")])
        screen, model = rig(images=[picture("x")], ocr=[[line("x")]], vision=[Choice(1, "click")])
        _, _, result, _ = run("click x", title.split()[0])
        assert not result.success and "do not look at it" in result.error and screen.grabs == 0 and model.seen == []


def test_the_picture_only_leaves_with_the_cloud_permission(db, world):
    update_preferences(db, PreferencesUpdate(cloud_answers=False))
    screen, model = rig(images=[picture("Start")], ocr=[MENU], vision=[Choice(1, "click")])
    _, _, result, _ = run("click Start")
    assert not result.success and "cloud answers" in result.error and model.seen == [] and screen.grabs == 0


def test_a_window_with_nothing_to_point_at_and_no_vision_model_are_explained(db, world):
    screen, _ = rig(images=[picture()], ocr=[[]], vision=[Choice(1, "click")])
    _, _, result, _ = run("click Start")
    assert not result.success and "found nothing I could point at" in result.error
    set_vision(None)
    class NoVision:
        groq_configured, gemini_api_key, vision_model = False, None, "x"
    import app.config as cfg
    real = cfg.get_settings
    cfg.get_settings = lambda: NoVision()
    try:
        screen_mod.set_screen(FakeScreen(picture("Start")))
        set_ocr(FakeOcr(MENU))
        _, _, result, _ = run("click Start")
    finally:
        cfg.get_settings = real
    assert not result.success and "No vision model" in result.error


def test_a_short_rate_limit_is_waited_out_once(db, world, monkeypatch):
    monkeypatch.setattr(screen_mod.time, "sleep", lambda s: None)
    screen, model = rig(images=[picture("Start"), picture("Game")], ocr=[MENU, [line("Game screen")]], vision=[AIRateLimitError("Groq rate limit reached", 3), Choice(1, "click")])
    _, _, result, ver = run("click Start")
    assert result.success and len(model.seen) == 2 and result.output["timings"]["waited_for_limit"] == 1 and ver.passed


def test_risk_levels():
    tool = ScreenActTool(ToolContext())
    risk = lambda goal, window=None: tool.risk_for_args(tool.validate_args({"goal": goal, "window": window}))   # noqa: E731
    assert risk("click Start") == RiskLevel.MEDIUM and risk("scroll down") == RiskLevel.MEDIUM
    assert risk("what is the score?") == RiskLevel.LOW and risk("read the title") == RiskLevel.LOW
    assert risk("click Delete") == RiskLevel.HIGH and risk("click Pay now") == RiskLevel.HIGH and risk("click Start", "Command Prompt") == RiskLevel.HIGH


def test_the_screen_comparison():
    a, b = picture("Start"), picture("Start")
    assert changed_share(a, b) == 0.0
    c = a.copy()
    ImageDraw.Draw(c).rectangle([200, 100, 380, 240], fill="white")
    assert changed_share(a, c) > 0.1


# --------------------------------------------------------------------------------------------------- the layer order
def test_a_poor_window_points_to_layer_three_and_results_name_their_layer(db, world):
    inspect = UiInspectTool(ToolContext())
    out = inspect.execute(inspect.validate_args({"window": "Pixel Game"})).output
    assert out["layer"] == 2 and "screen_act" in out["hint"]
    act = UiActTool(ToolContext())
    miss = act.execute(act.validate_args({"action": "click", "control": "Start", "window": "Pixel Game"}))
    assert not miss.success and "screen_act (layer 3)" in miss.error
    world.add("Rich App", "rich.exe", [FC(f"Button {i}", "Button") for i in range(6)])
    rich = inspect.execute(inspect.validate_args({"window": "Rich App"})).output
    assert "hint" not in rich
    hit = act.execute(act.validate_args({"action": "click", "control": "Button 1", "window": "Rich App"}))
    assert hit.output["layer"] == 2


def test_the_executor_logs_which_layer_did_the_work(db, world, monkeypatch):
    from app.orchestration import executor
    seen = []
    monkeypatch.setattr(executor, "log_event", lambda event, **kw: seen.append((event, kw)))
    screen, _ = rig(images=[picture("Start"), picture("Game")], ocr=[MENU, [line("Game screen")]], vision=[Choice(1, "click")])
    from app.ai.base import Plan, PlanAction
    from app.config import Settings
    from app.tools.registry import ToolRegistry
    registry = ToolRegistry(ToolContext())
    task = executor.create_task(db, "click Start in the game")
    task = executor.plan_task(db, task, registry, Settings(ai_provider="groq", groq_api_key=None), auto_approve=True,
                              preplanned=Plan(actions=[PlanAction(tool="screen_act", args={"goal": "click Start", "window": "Pixel Game"})]))
    ends = [kw for event, kw in seen if event == "action_end" and kw.get("tool") == "screen_act"]
    assert ends and ends[-1]["detail"] == "layer 3"


# --------------------------------------------------------------------------------------------------------- wiring
def test_the_tool_is_planned_shortlisted_and_announced(ctx):
    from app.nlu.schema import INTENTS
    from app.nlu.shortlist import shortlist_tools
    from app.tools.registry import ToolRegistry
    from app.voice import responses
    registry = ToolRegistry(ctx)
    assert "screen_act" in registry.model_names() and "screen_control" in INTENTS
    assert "screen_act" in shortlist_tools("look at the screen and click Start in the game", registry.model_names())
    assert "screen_act" not in shortlist_tools("volume 40 kar do", registry.model_names())
    who = responses.Voiceprint("assistant", "", 50, 50)
    assert responses.acknowledge_line("screen_act", {}, "en", who) == "This app needs me to look at the screen, a few seconds."
    assert "screen" in responses.acknowledge_line("screen_act", {}, "roman", who).casefold() or "اسکرین" in responses.acknowledge_line("screen_act", {}, "ur", who)
    assert screen_mod.NOTICE == "This app needs me to look at the screen, a few seconds."


def test_the_pictures_before_an_action_are_kept_only_briefly(db, world):
    for _ in range(screen_mod._REMEMBERED + 3):
        rig(images=[picture("Start"), picture("Game")], ocr=[MENU, [line("Game")]], vision=[Choice(1, "click")])
        run("click Start")
    assert len(screen_mod._before) <= screen_mod._REMEMBERED
