"""Execution orchestration: plan -> approve -> execute -> verify -> report.

Two flows share this module:

1. Static planning (mock provider): plan_task() plans everything up front,
   then run_task() executes the approved actions. Used by tests.
2. Agentic loop (Groq provider): start_agent_task() / continue_agent_task().
   The model proposes one tool call at a time; the backend validates it, the
   permission engine checks risk, low-risk tools execute immediately while
   medium/high-risk ones pause for user approval, and each result is fed
   back to the model for further reasoning. Loop state persists in
   Task.agent_state_json so it can pause and resume across HTTP requests.

State machine (tasks):
  created -> planned/awaiting_approval/approved -> executing -> completed/failed
  awaiting_approval -> approved (all pending approved) | rejected | cancelled
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import time

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..ai.base import AIError, AIRateLimitError, Plan
from ..ai.planner import get_provider, plan_command
from ..ai.tool_selection import tool_metadata
from ..config import Settings
from ..models import Action, ActionStatus, Task, TaskStatus, utcnow
from ..schemas import ActionOut, TaskOut
from ..security.permissions import needs_approval
from ..tools.base import RiskLevel, ToolResult, Verification
from ..tools.desktop import DesktopControlTool
from ..tools.registry import ToolRegistry, UnknownToolError


# ---------------------------------------------------------------- serialization
def _action_out(a: Action) -> ActionOut:
    return ActionOut(
        id=a.id,
        seq=a.seq,
        tool_name=a.tool_name,
        args=json.loads(a.args_json or "{}"),
        risk=a.risk,
        status=a.status,
        result=json.loads(a.result_json) if a.result_json else None,
        verification=json.loads(a.verification_json) if a.verification_json else None,
        error=a.error,
    )


def task_out(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        command=task.command,
        status=task.status,
        plan_note=task.plan_note,
        error=task.error,
        created_at=task.created_at,
        updated_at=task.updated_at,
        retry_at=_agent_state(task).get("retry_at"),
        provider_note=_agent_state(task).get("provider_note"),
        actions=[_action_out(a) for a in sorted(task.actions, key=lambda x: x.seq)],
    )


def _get_task(db: Session, task_id: str) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise KeyError(f"Task '{task_id}' not found")
    return task


def _risk_for_task_action(tool, parsed_args, command: str) -> RiskLevel:
    if isinstance(tool, DesktopControlTool):
        return tool.risk_for_user_command(parsed_args, command)
    return tool.risk_for_args(parsed_args)


# ------------------------------------------------------------------ lifecycle
def create_task(db: Session, command: str, idempotency_key: str | None = None) -> Task:
    """Create a task; an existing idempotency key returns the original task."""
    if idempotency_key:
        existing = db.query(Task).filter(Task.idempotency_key == idempotency_key).first()
        if existing:
            return existing
    task = Task(command=command, idempotency_key=idempotency_key, status=TaskStatus.CREATED)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def plan_task(db: Session, task: Task, registry: ToolRegistry, settings: Settings, auto_approve: bool = False, preplanned: Plan | None = None) -> Task:
    """Generate + validate a plan and persist the planned actions."""
    try:
        if preplanned is None:
            provider = get_provider(settings)
            plan: Plan = plan_command(task.command, registry, provider)
        else:
            plan = preplanned
            for action in plan.actions:
                registry.get(action.tool).validate_args(action.args)
    except (AIError, ValidationError, UnknownToolError) as exc:
        task.status = TaskStatus.FAILED
        task.error = str(exc)
        task.updated_at = utcnow()
        db.commit()
        db.refresh(task)
        return task

    # Meta-command: report the previous task's result.
    if plan.note == "__PREVIOUS_TASK__":
        prev = (
            db.query(Task)
            .filter(Task.id != task.id, Task.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED]))
            .order_by(Task.created_at.desc())
            .first()
        )
        if prev:
            done = sum(1 for a in prev.actions if a.status == ActionStatus.SUCCEEDED)
            task.plan_note = (
                f"Previous task '{prev.command}' finished with status '{prev.status}': "
                f"{done}/{len(prev.actions)} actions succeeded."
            )
        else:
            task.plan_note = "There is no previous finished task yet."
        task.status = TaskStatus.COMPLETED
        db.commit()
        db.refresh(task)
        return task

    # Clarification / informational plans carry no actions.
    if not plan.actions:
        task.plan_note = plan.note or "No actions were planned for this command."
        task.status = TaskStatus.AWAITING_INPUT if preplanned is not None else TaskStatus.COMPLETED
        db.commit()
        db.refresh(task)
        return task

    task.plan_note = plan.note
    if getattr(plan, "mock", False):
        prefix = "[mock AI] "
        task.plan_note = (prefix + (task.plan_note or "")).strip()
    any_pending = False
    for seq, action in enumerate(plan.actions):
        tool = registry.get(action.tool)
        parsed = tool.validate_args(action.args)
        risk = _risk_for_task_action(tool, parsed, task.command)
        status = ActionStatus.APPROVED if auto_approve else (ActionStatus.PENDING if needs_approval(risk) else ActionStatus.APPROVED)
        any_pending = any_pending or status == ActionStatus.PENDING
        db.add(
            Action(
                task_id=task.id,
                seq=seq,
                tool_name=action.tool,
                args_json=json.dumps(action.args),
                risk=risk.value,
                status=status,
            )
        )
    task.status = TaskStatus.AWAITING_APPROVAL if any_pending else TaskStatus.APPROVED
    db.commit()
    db.refresh(task)
    if auto_approve and task.status == TaskStatus.APPROVED and task.actions:
        return run_task(db, task.id, registry, settings)
    return task


def approve_task(db: Session, task_id: str, action_ids: list[str] | None = None) -> Task:
    task = _get_task(db, task_id)
    if task.status not in (TaskStatus.AWAITING_APPROVAL, TaskStatus.APPROVED, TaskStatus.PLANNED):
        raise ValueError(f"Task '{task_id}' is '{task.status}' and cannot be approved now")
    targets = [a for a in task.actions if a.status == ActionStatus.PENDING]
    if action_ids is not None:
        wanted = set(action_ids)
        targets = [a for a in targets if a.id in wanted]
    for a in targets:
        a.status = ActionStatus.APPROVED
    remaining = [a for a in task.actions if a.status == ActionStatus.PENDING]
    task.status = TaskStatus.APPROVED if not remaining else TaskStatus.AWAITING_APPROVAL
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)
    return task



def reject_task(db: Session, task_id: str, action_ids: list[str] | None = None) -> Task:
    task = _get_task(db, task_id)
    if task.status not in (TaskStatus.AWAITING_APPROVAL, TaskStatus.APPROVED, TaskStatus.PLANNED):
        raise ValueError(f"Task '{task_id}' is '{task.status}' and cannot be rejected now")
    targets = [a for a in task.actions if a.status in (ActionStatus.PENDING, ActionStatus.APPROVED)]
    if action_ids is not None:
        wanted = set(action_ids)
        targets = [a for a in targets if a.id in wanted]
    for a in targets:
        a.status = ActionStatus.REJECTED
    task.status = TaskStatus.REJECTED
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)
    return task


def cancel_task(db: Session, task_id: str) -> Task:
    task = _get_task(db, task_id)
    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
        return task  # already terminal; nothing to cancel
    for a in task.actions:
        if a.status in (ActionStatus.PENDING, ActionStatus.APPROVED):
            a.status = ActionStatus.CANCELLED
    task.status = TaskStatus.CANCELLED
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)
    return task


# ------------------------------------------------------------------ execution
def _run_with_timeout(tool, parsed_args, timeout_seconds: int) -> ToolResult:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(tool.execute, parsed_args)
        try:
            return future.result(timeout=max(timeout_seconds, 250) if tool.name == "application_package" else timeout_seconds)
        except concurrent.futures.TimeoutError:
            return ToolResult(success=False, error=f"Tool timed out after {timeout_seconds}s")


def run_task(db: Session, task_id: str, registry: ToolRegistry, settings: Settings) -> Task:
    """Execute approved actions in order, verifying each one.

    Duplicate-execution prevention: terminal tasks are returned unchanged,
    and a task is only runnable from an approved state with no pending actions.
    """
    task = _get_task(db, task_id)
    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.REJECTED):
        return task  # already finished; never re-execute
    pending = [a for a in task.actions if a.status == ActionStatus.PENDING]
    if pending:
        raise ValueError(
            f"Task '{task_id}' still has {len(pending)} action(s) awaiting approval"
        )
    runnable = [a for a in sorted(task.actions, key=lambda x: x.seq) if a.status == ActionStatus.APPROVED]
    if not runnable and task.status not in (TaskStatus.APPROVED,):
        raise ValueError(f"Task '{task_id}' has no approved actions to run")

    task.status = TaskStatus.EXECUTING
    task.updated_at = utcnow()
    db.commit()

    failed = False
    for action in runnable:
        # Refresh: a cancel may have landed between actions.
        db.refresh(task)
        if task.status == TaskStatus.CANCELLED:
            action.status = ActionStatus.CANCELLED
            db.commit()
            break
        tool = registry.get(action.tool_name)
        parsed = tool.validate_args(json.loads(action.args_json or "{}"))
        _execute_single_action(db, action, tool, parsed, settings)
        if action.status == ActionStatus.FAILED:
            failed = True
            break  # never continue blindly after a failure

    if failed:
        for a in runnable:
            if a.status == ActionStatus.APPROVED:
                a.status = ActionStatus.SKIPPED
        task.status = TaskStatus.FAILED
        failed_action = next((a for a in runnable if a.status == ActionStatus.FAILED), None)
        task.error = failed_action.error if failed_action else "One or more actions failed; remaining actions were skipped."
        if failed_action and json.loads(failed_action.result_json or "{}").get("output", {}).get("needs_confirmation"):
            task.status = TaskStatus.AWAITING_INPUT
            task.plan_note = task.error
            task.error = None
    elif task.status == TaskStatus.CANCELLED:
        pass  # keep cancellation
    else:
        task.status = TaskStatus.COMPLETED
        task.error = None
        if _agent_state(task).get("provider") == "local" and not _agent_state(task).get("workflow"):
            last = next((a for a in reversed(runnable) if a.status == ActionStatus.SUCCEEDED), None)
            if last:
                output = json.loads(last.result_json or "{}").get("output", {})
                if last.tool_name == "manage_system_setting":
                    setting = output.get("setting", "Setting")
                    if "value" in output:
                        task.plan_note = f"{setting.capitalize()} ab {output['value']}% hai."
                    elif "muted" in output:
                        task.plan_note = "Volume mute kar diya." if output["muted"] else "Volume unmute kar diya."
                    elif "enabled" in output:
                        task.plan_note = "Bluetooth on hai." if output["enabled"] else "Bluetooth off hai."
                    else:
                        task.plan_note = f"Windows/app theme: {output.get('system', '')}/{output.get('apps', '')}."
                elif last.tool_name == "application_package":
                    task.plan_note = output.get("details", "Package operation complete.")[:6000]
                elif last.tool_name == "control_browser":
                    if output.get("tabs") is not None:
                        task.plan_note = "\n".join(f"tab {t['id']}: {t.get('title', '')}" for t in output["tabs"]) or "Koi tab nahi mila."
                    else:
                        task.plan_note = {"pause": "YouTube video pause kar di.", "resume": "YouTube video resume kar di.", "close": "Requested tab band kar diya."}.get(output.get("action"), "Browser command complete.")
                elif last.tool_name == "play_youtube_video":
                    task.plan_note = output.get("message", "YouTube page khol diya; playback verify karein.")
                else:
                    task.plan_note = f"Kaam complete: {last.tool_name.replace('_', ' ')}."
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)
    return task


# ------------------------------------------------------------------ shared
def _execute_single_action(db: Session, action: Action, tool, parsed, settings: Settings) -> None:
    """Run one approved action with timeout, then verify it. Commits."""
    action.status = ActionStatus.RUNNING
    db.commit()
    result = _run_with_timeout(tool, parsed, settings.tool_timeout_seconds)
    action.result_json = result.model_dump_json()
    verification = (
        tool.verify(parsed, result)
        if result.success
        else Verification(passed=False, checks=[], details=result.error)
    )
    action.verification_json = verification.model_dump_json()
    if result.success and verification.passed:
        action.status = ActionStatus.SUCCEEDED
    else:
        action.status = ActionStatus.FAILED
        action.error = result.error or f"Verification failed: {'; '.join(verification.checks)}"
    db.commit()


# ------------------------------------------------------------------ agentic loop (Groq)
def _agent_state(task: Task) -> dict:
    if task.agent_state_json:
        try:
            return json.loads(task.agent_state_json)
        except json.JSONDecodeError:
            pass
    return {}


def _save_agent_state(db: Session, task: Task, state: dict) -> None:
    task.agent_state_json = json.dumps(state)
    task.updated_at = utcnow()
    db.commit()


def _fingerprint(tool_name: str, args: dict) -> str:
    return hashlib.sha256(
        f"{tool_name}:{json.dumps(args, sort_keys=True)}".encode()
    ).hexdigest()


def _tool_result_message(call_id: str, ok: bool, detail: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps({"success": ok, "detail": detail[:16000]}),
    }


def _action_summary(action: Action) -> str:
    parts = []
    if action.result_json:
        try:
            output = json.loads(action.result_json).get("output", {})
            parts.append("output=" + json.dumps(output)[:14000])
        except (json.JSONDecodeError, AttributeError):
            pass
    if action.verification_json:
        try:
            v = json.loads(action.verification_json)
            parts.append(
                "verification_passed=" + str(v.get("passed"))
                + "; checks=" + "; ".join(v.get("checks", []))
            )
        except (json.JSONDecodeError, AttributeError):
            pass
    if action.error:
        parts.append("error=" + action.error[:500])
    return "; ".join(parts) or "done"


def start_task(
    db: Session, command: str, idempotency_key: str | None,
    registry: ToolRegistry, settings: Settings,
    auto_approve: bool = False,
) -> Task:
    """Create a task and start the right flow for the configured provider."""
    task = create_task(db, command, idempotency_key)
    if task.status != TaskStatus.CREATED:
        return task  # idempotency key matched an existing task
    if settings.ai_provider.strip().lower() != "mock":
        from .local_agent import prepare_local_request
        local = prepare_local_request(db, task, registry)
        if local is not None:
            if not task.agent_state_json:
                task.agent_state_json = json.dumps({"provider": "local"})
            task = plan_task(db, task, registry, settings, auto_approve=auto_approve, preplanned=local)
            if task.status == TaskStatus.APPROVED:
                return run_task(db, task.id, registry, settings)
            return task
        if settings.ai_cloud_mode != "automatic" and not command.strip().casefold().startswith(("ai:", "research ", "explain ")):
            return plan_task(db, task, registry, settings, preplanned=Plan(note="Local agent ko yeh command clear nahi hui. App/file ka naam aur operation batayein. Detailed AI reasoning ke liye 'AI:' ya 'research' se request shuru karein."))
    try:
        provider = get_provider(settings)
    except AIError as exc:
        # No silent fallback: a misconfigured provider fails the task loudly.
        task.status = TaskStatus.FAILED
        task.error = str(exc)
        task.updated_at = utcnow()
        db.commit()
        db.refresh(task)
        return task
    from ..ai.groq_provider import GroqProvider

    if isinstance(provider, GroqProvider):
        return start_agent_task(db, task, registry, provider, settings, auto_approve=auto_approve)
    return plan_task(db, task, registry, settings, auto_approve=auto_approve)


def _session_user_message(db: Session, task: Task) -> str:
    """Keep a short conversation memory so confirmations continue the work."""
    previous = (
        db.query(Task)
        .filter(Task.id != task.id)
        .order_by(Task.created_at.desc())
        .limit(4)
        .all()
    )
    if not previous:
        return task.command
    blocks = []
    for prior in reversed(previous):
        reply = (prior.plan_note or prior.error or prior.status or "").strip()
        if not prior.command:
            continue
        observations = []
        for action in sorted(prior.actions, key=lambda a: a.seq)[-6:]:
            observations.append({"tool": action.tool_name, "args": json.loads(action.args_json or "{}"),
                                 "status": action.status, "result": json.loads(action.result_json or "{}")})
        blocks.append(f"User: {prior.command}\nAssistant: {reply[:2000] or prior.status}\nObserved tools: "
                      + json.dumps(observations, ensure_ascii=False)[:4000])
    return (
        "Recent conversation (if the user is confirming a suggested app, file, "
        "folder, window, or next step, perform that original work now):\n"
        + "\n\n".join(blocks)
        + f"\n\nLatest user message: {task.command}"
    )


def start_agent_task(
    db: Session, task: Task, registry: ToolRegistry, provider, settings: Settings,
    auto_approve: bool = False,
) -> Task:
    """Run the agentic loop until the model finishes or approval is needed."""
    from ..ai.groq_provider import GroqProvider, SYSTEM_PROMPT

    assert isinstance(provider, GroqProvider)
    specs = GroqProvider.build_tool_specs(tool_metadata(registry, task.command))
    state = {
        "provider": "groq",
        "auto_approve": auto_approve,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _session_user_message(db, task)},
        ],
        "fingerprints": [],
        "rejections_reported": [],
        "steps": 0,
    }
    task.status = TaskStatus.EXECUTING
    db.commit()
    try:
        return _agent_loop(db, task, registry, provider, settings, specs, state)
    except AIError as exc:
        # Groq failure: fail loudly, never fall back to mock.
        if isinstance(exc, AIRateLimitError):
            task.status = TaskStatus.WAITING_RETRY
            state["retry_at"] = time.time() + exc.retry_after
            task.plan_note = "AI quota ki wajah se task pause hai. Reset time ke baad Resume dabayein; simple volume/brightness commands abhi bhi chalengi."
            task.error = None
        else:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
        _save_agent_state(db, task, state)
        db.refresh(task)
        return task


def _agent_loop(db, task, registry, provider, settings, specs, state) -> Task:
    max_steps = settings.agent_max_steps
    while state["steps"] < max_steps:
        db.refresh(task)
        if task.status == TaskStatus.CANCELLED:
            _save_agent_state(db, task, state)
            return task
        # May raise AIError -> caught by the caller, task fails loudly.
        resp = provider.complete(state["messages"], tools=specs)
        state.pop("retry_at", None)
        if getattr(provider, "notice", None):
            state["provider_note"] = provider.notice
        state["steps"] += 1
        tool_calls = resp.get("tool_calls") or []
        if not tool_calls:
            # Model finished (or is asking the user a question).
            task.plan_note = resp.get("content") or "Done."
            state["messages"].append({"role": "assistant", "content": task.plan_note})
            task.status = TaskStatus.COMPLETED
            task.error = None
            _save_agent_state(db, task, state)
            db.refresh(task)
            return task
        state["messages"].append(
            {
                "role": "assistant",
                "content": resp.get("content"),
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["raw_arguments"]},
                        **({"extra_content": tc["extra_content"]} if tc.get("extra_content") else {}),
                    }
                    for tc in tool_calls
                ],
            }
        )
        paused = False
        for tc in tool_calls:
            # Validate independently of the model - never trust it blindly.
            try:
                tool = registry.get(tc["name"])
            except UnknownToolError as exc:
                state["messages"].append(
                    _tool_result_message(tc["id"], False, f"Unknown tool rejected: {exc}")
                )
                continue
            try:
                parsed = tool.validate_args(tc["arguments"])
            except ValidationError as exc:
                state["messages"].append(
                    _tool_result_message(tc["id"], False, f"Invalid arguments rejected: {exc}")
                )
                continue
            fp = _fingerprint(tc["name"], tc["arguments"])
            if fp in state["fingerprints"]:
                state["messages"].append(
                    _tool_result_message(tc["id"], True, "Already executed - not repeated.")
                )
                continue
            risk = _risk_for_task_action(tool, parsed, task.command)
            seq = len(task.actions)
            auto_approved = state.get("auto_approve", False)
            if needs_approval(risk) and not auto_approved:
                db.add(
                    Action(
                        task_id=task.id,
                        seq=seq,
                        tool_name=tc["name"],
                        args_json=json.dumps(tc["arguments"]),
                        risk=risk.value,
                        status=ActionStatus.PENDING,
                        call_id=tc["id"],
                    )
                )
                task.status = TaskStatus.AWAITING_APPROVAL
                paused = True
                continue  # still answer every other tool_call id this turn
            action = Action(
                task_id=task.id,
                seq=seq,
                tool_name=tc["name"],
                args_json=json.dumps(tc["arguments"]),
                risk=risk.value,
                status=ActionStatus.APPROVED,
                call_id=tc["id"],
            )
            db.add(action)
            db.commit()
            _execute_single_action(db, action, tool, parsed, settings)
            state["fingerprints"].append(fp)
            state["messages"].append(
                _tool_result_message(
                    tc["id"], action.status == ActionStatus.SUCCEEDED, _action_summary(action)
                )
            )
        _save_agent_state(db, task, state)
        db.refresh(task)
        if paused:
            return task
    task.status = TaskStatus.FAILED
    task.error = (
        f"Agent exceeded the maximum of {max_steps} tool steps without finishing. "
        "Try a smaller request."
    )
    _save_agent_state(db, task, state)
    db.refresh(task)
    return task


def continue_agent_task(db: Session, task_id: str, registry: ToolRegistry, provider, settings: Settings) -> Task:
    """Resume a paused agentic loop after approval/rejection, then keep going."""
    task = _get_task(db, task_id)
    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.REJECTED):
        return task  # terminal: never re-execute
    state = _agent_state(task)
    if not state or state.get("provider") != "groq":
        return run_task(db, task_id, registry, settings)  # not an agent task
    if task.status == TaskStatus.WAITING_RETRY and time.time() < state.get("retry_at", 0):
        return task  # Respect the provider reset even if Resume is pressed repeatedly.
    pending = [a for a in task.actions if a.status == ActionStatus.PENDING]
    if pending:
        raise ValueError(
            f"Task '{task_id}' still has {len(pending)} action(s) awaiting approval"
        )
    from ..ai.groq_provider import GroqProvider

    specs = GroqProvider.build_tool_specs(tool_metadata(registry, task.command))
    # Execute newly-approved actions and report rejections back to the model.
    for action in sorted(task.actions, key=lambda x: x.seq):
        if action.status == ActionStatus.APPROVED and action.call_id:
            fp = _fingerprint(action.tool_name, json.loads(action.args_json or "{}"))
            if fp in state.get("fingerprints", []):
                action.status = ActionStatus.SKIPPED
                db.commit()
                continue
            tool = registry.get(action.tool_name)
            parsed = tool.validate_args(json.loads(action.args_json or "{}"))
            _execute_single_action(db, action, tool, parsed, settings)
            state["fingerprints"].append(fp)
            state["messages"].append(
                _tool_result_message(
                    action.call_id, action.status == ActionStatus.SUCCEEDED, _action_summary(action)
                )
            )
        elif action.status == ActionStatus.REJECTED and action.call_id:
            if action.call_id not in state.get("rejections_reported", []):
                state["messages"].append(
                    _tool_result_message(
                        action.call_id,
                        False,
                        "The user rejected this action. Do not retry it; adjust the plan or explain.",
                    )
                )
                state["rejections_reported"].append(action.call_id)
    task.status = TaskStatus.EXECUTING
    db.commit()
    try:
        return _agent_loop(db, task, registry, provider, settings, specs, state)
    except AIError as exc:
        if isinstance(exc, AIRateLimitError):
            task.status = TaskStatus.WAITING_RETRY
            state["retry_at"] = time.time() + exc.retry_after
            task.plan_note = "AI quota ki wajah se task pause hai. Reset time ke baad Resume dabayein; simple volume/brightness commands abhi bhi chalengi."
            task.error = None
        else:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
        _save_agent_state(db, task, state)
        db.refresh(task)
        return task
