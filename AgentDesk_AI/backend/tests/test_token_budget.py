"""Groq's free tier: one request may not exceed 8,000 tokens per minute on gpt-oss-120b. The whole tool catalogue is ~8,100 tokens, so the
request must carry only the tools the command could need, in every language, and a 413 must be retried with a smaller one."""
from __future__ import annotations

import json

import pytest
from tests.test_agent_loop import _loop_harness, _turn

from app.ai.base import AIError
from app.ai.tool_selection import RETRY_BUDGET, TOOLS_BUDGET, estimate_tokens, tool_metadata
from app.models import TaskStatus
from app.orchestration import executor
from app.tools.registry import ToolRegistry

COMMANDS = [
    "تم گزارش میوزک پلے کر دو",                                          # the real failing Urdu command
    "मैं आपको कह रहा हूँ कि यूट्यूब के ऊपर गुजारिश म्यूजिक प्ले कर दो",         # Hindi script
    "Ab gazaarish music ishi YouTube page ke oper search karo",        # Roman Urdu
    "antigravity kholo aur ye prompt do",
    "haan woh wala",                                                   # a confirmation: no tool words at all
    "create a folder called Notes in Documents and then zip it",
]


@pytest.mark.parametrize("command", COMMANDS)
def test_every_language_gets_a_small_tool_list(command):
    registry = ToolRegistry()
    chosen = tool_metadata(registry, command)
    assert len(chosen) < len(registry.metadata())
    assert estimate_tokens(chosen) <= TOOLS_BUDGET                    # far below the ~8,100 of the whole catalogue
    assert estimate_tokens(registry.metadata()) > 8000                 # why the old code failed: the catalogue alone is over the limit


def test_urdu_and_hindi_music_commands_reach_the_youtube_tools():
    registry = ToolRegistry()
    for command in (COMMANDS[0], COMMANDS[1], COMMANDS[2]):
        names = {t["name"] for t in tool_metadata(registry, command)}
        assert names & {"play_youtube_video", "control_browser"}, (command, names)


def test_a_confirmation_keeps_the_previous_tasks_tools():
    names = {t["name"] for t in tool_metadata(ToolRegistry(), "haan woh wala", ["delete_file"])}
    assert "delete_file" in names


def test_the_budget_drops_the_heaviest_tool_first_and_keeps_the_basics():
    registry = ToolRegistry()
    tight = tool_metadata(registry, "youtube pe gana chalao aur tab band karo", budget=RETRY_BUDGET)
    assert estimate_tokens(tight) <= RETRY_BUDGET and len(tight) >= 4
    assert "open_application" in {t["name"] for t in tight}


def test_a_413_is_retried_once_with_fewer_tools(db, tmp_path):
    error = AIError("Groq API error: Error code: 413 - {'error': {'message': 'Request too large for model `openai/gpt-oss-120b` on tokens per minute (TPM): "
                      "Limit 8000, Requested 8985'}}")
    registry, settings, provider = _loop_harness(db, tmp_path, [error, _turn(content="Done.")])
    sent = []
    create = provider._client.chat.completions.create

    def spy(**kwargs):
        sent.append(len(kwargs.get("tools") or []))
        return create(**kwargs)

    provider._client.chat.completions.create = spy
    task = executor.create_task(db, "tum guzarish music play kar do")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    assert task.status == TaskStatus.COMPLETED and task.plan_note == "Done."
    assert len(sent) == 2 and sent[1] <= sent[0]
    assert json.loads(task.agent_state_json)["steps"] == 1


def test_a_413_that_keeps_happening_fails_loudly_not_forever(db, tmp_path):
    error = AIError("Groq API error: Error code: 413 - Request too large ... Limit 8000, Requested 9500")
    registry, settings, provider = _loop_harness(db, tmp_path, [error, error])
    task = executor.create_task(db, "kuch bhi")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    assert task.status == TaskStatus.FAILED and "413" in (task.error or "")


def test_an_agent_that_keeps_failing_stops_instead_of_burning_the_quota(db, tmp_path):
    """Seen live: the agent retried play_youtube_video five times with new search words, one AI call (a few thousand tokens) each."""
    from tests.test_agent_loop import _tc
    bad = [_turn(_tc(f"c{i}", "read_text_file", {"path": str(tmp_path / f"missing{i}.txt")})) for i in range(8)]
    registry, settings, provider = _loop_harness(db, tmp_path, [*bad, _turn(content="never reached")], agent_max_steps=20)
    task = executor.create_task(db, "read my notes")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    assert task.status == TaskStatus.FAILED and "last 3 steps failed" in task.error
    assert len(task.actions) == 3                                      # stopped after the third failure, not after 20 steps
