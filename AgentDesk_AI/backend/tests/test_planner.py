"""Tests for AI planning: mock provider behaviour and plan validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.base import AIError, Plan, PlanAction
from app.ai.mock_provider import MockProvider
from app.ai.planner import get_provider, plan_command
from app.config import get_settings
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


@pytest.fixture()
def registry(tmp_path: Path) -> ToolRegistry:
    return ToolRegistry(ToolContext(allowed_directories=[tmp_path], approved_applications=["chrome"], test_dir=tmp_path))


def test_mock_provider_is_labelled(tmp_path: Path):
    provider = MockProvider(home=tmp_path)
    plan = provider.generate_plan("open Chrome", "")
    assert plan.mock is True
    assert provider.is_mock


def test_mock_plans_example_commands(tmp_path: Path, registry: ToolRegistry):
    provider = MockProvider(home=tmp_path)
    cases = {
        "Open Chrome": ("open_application", {"app_name": "Chrome"}),
        "Open email": ("open_application", {"app_name": "mail"}),
        "Open the email app": ("open_application", {"app_name": "mail"}),
        "Open my Downloads folder": ("open_folder", {"path": str(tmp_path / "Downloads")}),
        "Create folder name is ai in destop": (
            "create_folder",
            {"path": str(tmp_path / "Desktop" / "ai")},
        ),
        "Create a folder called FYP in Documents": ("create_folder", {"path": str(tmp_path / "Documents" / "FYP")}),
        f"Copy the file {tmp_path / 'source.txt'} to {tmp_path / 'backup.txt'}": (
            "copy_file",
            {"source": str(tmp_path / "source.txt"), "destination": str(tmp_path / "backup.txt")},
        ),
        "Draft an email to user@example.com with subject Update and body Hello there": (
            "compose_email",
            {"to": "user@example.com", "subject": "Update", "body": "Hello there"},
        ),
        "Open the website example.com": ("open_url", {"url": "https://example.com"}),
    }
    for command, (tool, args) in cases.items():
        plan = plan_command(command, registry, provider)
        assert len(plan.actions) == 1, command
        assert plan.actions[0].tool == tool, command
        assert plan.actions[0].args == args, command


def test_mock_marks_previous_task(tmp_path: Path):
    plan = MockProvider(home=tmp_path).generate_plan("Show the result of the previous task", "")
    assert plan.actions == [] and plan.note == "__PREVIOUS_TASK__"


def test_mock_asks_for_clarification(tmp_path: Path, registry: ToolRegistry):
    plan = plan_command("Rename a document", registry, MockProvider(home=tmp_path))
    assert plan.actions == []
    assert plan.note  # a helpful question, not a crash


def test_unknown_tool_rejected(tmp_path: Path, registry: ToolRegistry):
    class EvilProvider(MockProvider):
        def generate_plan(self, command, tool_descriptions):
            return Plan(actions=[PlanAction(tool="format_drive", args={})], mock=True)

    with pytest.raises(AIError, match="Unknown tool"):
        plan_command("do evil", registry, EvilProvider(home=tmp_path))


def test_invalid_args_rejected(tmp_path: Path, registry: ToolRegistry):
    class SloppyProvider(MockProvider):
        def generate_plan(self, command, tool_descriptions):
            return Plan(actions=[PlanAction(tool="open_url", args={"url": "not a url"})], mock=True)

    with pytest.raises(AIError, match="invalid arguments"):
        plan_command("open it", registry, SloppyProvider(home=tmp_path))


def test_get_provider_mock_by_default():
    settings = get_settings()
    assert settings.ai_provider == "mock"
    assert get_provider(settings).is_mock


def test_get_provider_openai_without_key_errors():
    from app.ai.planner import get_provider as gp
    from app.config import Settings

    s = Settings(ai_provider="openai", openai_api_key=None)
    with pytest.raises(Exception, match="OPENAI_API_KEY"):
        gp(s)


def test_get_provider_unknown_name_errors():
    from app.ai.planner import get_provider as gp
    from app.config import Settings

    with pytest.raises(Exception, match="Unknown AI_PROVIDER"):
        gp(Settings(ai_provider="watson"))
