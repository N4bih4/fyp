"""Shadow (team lead) hands each request to the right FREE agent, and moves a job when the named agent is busy."""
from __future__ import annotations

from app.agents.dispatcher import Dispatcher, address, kind_of_work
from app.agents.roster import load_roster
from app.models import Task, TaskStatus


class FakeDb:
    """Just enough of a Session: db.get(Task, id)."""

    def __init__(self):
        self.tasks: dict[str, Task] = {}

    def get(self, _model, task_id):
        return self.tasks.get(task_id)

    def add(self, task_id: str, status: str) -> None:
        self.tasks[task_id] = Task(id=task_id, command="x", status=status)


def test_five_agents_and_one_lead():
    team = load_roster()
    assert [a.name for a in team] == ["Shadow", "Scout", "Atlas", "Forge", "Echo"]
    assert [a.name for a in team if a.is_lead] == ["Shadow"]


def test_a_name_at_the_start_picks_the_agent_and_is_removed():
    team = load_roster()
    agent, body = address("Scout, search chairs on Daraz", team)
    assert agent.name == "Scout" and body == "search chairs on Daraz"
    assert address("शैडो एंटी ग्रेविटी खोलो", team)[0].name == "Shadow"
    assert address("شیڈو کروم کھولو", team)[0].name == "Shadow"
    assert address("open the scout folder", team)[0] is None      # only a name at the start counts
    assert address("Scout", team)[0] is None                       # a bare name with no request is not an order


def test_kind_of_work_in_four_languages():
    assert kind_of_work("youtube pe gana chalao") == "browser"
    assert kind_of_work("create a folder in Documents") == "files"
    assert kind_of_work("volume kam karo") == "system"
    assert kind_of_work("antigravity kholo aur prompt do") == "coding"
    assert kind_of_work("एंटी ग्रेविटी खोलो") == "coding"
    assert kind_of_work("इसकी स्टोरी की समरी दो") == "research"


def test_best_free_agent_gets_the_work_and_the_lead_comes_last():
    d, db = Dispatcher(load_roster()), FakeDb()
    assert d.choose(db, "youtube kholo")[0].agent == "Scout"
    assert d.choose(db, "antigravity kholo")[0].agent == "Forge"
    assert d.choose(db, "volume kam karo")[0].agent == "Atlas"


def test_busy_agent_work_moves_to_a_free_one_with_the_same_skill():
    d, db = Dispatcher(load_roster()), FakeDb()
    first, _ = d.choose(db, "youtube kholo")
    db.add("t1", TaskStatus.EXECUTING)
    d.record(first, "t1")
    second, _ = d.choose(db, "search chairs on daraz")           # Scout is busy: Echo/Atlas can browse too
    assert second.agent in {"Echo", "Atlas"} and not second.queued
    named, body = d.choose(db, "Scout, open youtube and play a song")
    assert named.agent != "Scout" and "busy" in named.note and body == "open youtube and play a song"


def test_a_finished_task_frees_the_agent():
    d, db = Dispatcher(load_roster()), FakeDb()
    a, _ = d.choose(db, "youtube kholo")
    db.add("t1", TaskStatus.EXECUTING)
    d.record(a, "t1")
    assert d.choose(db, "youtube kholo")[0].agent != "Scout"
    db.tasks["t1"].status = TaskStatus.COMPLETED
    assert d.choose(db, "youtube kholo")[0].agent == "Scout"


def test_when_everyone_who_can_is_busy_the_job_queues_with_the_best():
    d, db = Dispatcher(load_roster()), FakeDb()
    for i, name in enumerate(["Scout", "Echo", "Atlas", "Forge", "Shadow"]):
        a = d.choose(db, f"{name}, youtube kholo")[0]
        a.agent = name
        db.add(f"t{i}", TaskStatus.EXECUTING)
        d.record(a, f"t{i}")
    last, _ = d.choose(db, "youtube kholo")
    assert last.queued and last.agent == "Scout"


def test_status_lists_every_agent_with_what_it_is_doing():
    d, db = Dispatcher(load_roster()), FakeDb()
    a, _ = d.choose(db, "youtube kholo")
    db.add("t1", TaskStatus.EXECUTING)
    d.record(a, "t1")
    rows = {r["name"]: r for r in d.status(db)}
    assert rows["Scout"]["busy"] and rows["Scout"]["task_id"] == "t1" and not rows["Atlas"]["busy"]
