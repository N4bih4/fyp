"""AgentDesk AI backend: FastAPI application and HTTP API."""
from __future__ import annotations

import platform
import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db, init_db, SessionLocal
from .models import Task, TaskStatus, ActionStatus, utcnow
from .orchestration import executor
from .schemas import (
    ActionOut,
    ApprovalRequest,
    ConfigStatusOut,
    HealthOut,
    TaskCreate,
    TaskReply,
    TaskOut,
)
from .tools.base import ToolContext
from .tools.registry import ToolRegistry
from .browser_bridge import router as browser_router, bridge

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # The launcher runs one server. Never leave a crashed task showing as active
    # or replay its possibly completed device/file operation after restart.
    with SessionLocal() as db:
        for task in db.query(Task).filter(Task.status == TaskStatus.EXECUTING).all():
            task.status = TaskStatus.FAILED
            task.error = "Server restart se task interrupt hua. Result verify karke nayi command dein."
            task.updated_at = utcnow()
            for action in task.actions:
                if action.status == ActionStatus.RUNNING:
                    action.status = ActionStatus.FAILED
                    action.error = task.error
                elif action.status == ActionStatus.APPROVED:
                    action.status = ActionStatus.SKIPPED
        db.commit()
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.include_router(browser_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list({settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"}),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _registry() -> ToolRegistry:
    return ToolRegistry(ToolContext.from_settings())


# ------------------------------------------------------------------ health
@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok", version=settings.app_version)


@app.get("/config/status", response_model=ConfigStatusOut)
def config_status() -> ConfigStatusOut:
    # Never expose any API key - only whether one is configured.
    s = get_settings()
    provider = s.ai_provider.strip().lower()
    if s.is_mock_mode:
        ai_configured = True  # mock always works; it is explicitly selected
    elif provider == "groq":
        ai_configured = s.groq_configured
    else:
        ai_configured = bool(s.openai_api_key)
    return ConfigStatusOut(
        ai_provider=s.ai_provider,
        ai_model=s.ai_model,
        ai_configured=ai_configured,
        mock_mode=s.is_mock_mode,
        groq_configured=s.groq_configured,
        agent_max_steps=s.agent_max_steps,
        fallback_provider=s.ai_fallback_provider,
        cloud_mode=s.ai_cloud_mode,
        browser_connected=len(bridge.clients) == 1,
        browser_profiles=len(bridge.clients),
        fallback_configured=bool((s.ai_fallback_provider == "gemini" and s.gemini_api_key) or (s.ai_fallback_provider == "openai" and s.openai_api_key)),
        allowed_directories=[str(p) for p in s.resolved_allowed_directories()],
        approved_applications=s.resolved_approved_applications(),
        platform=platform.system(),
    )


@app.get("/tools", response_model=list[dict])
def list_tools() -> list[dict]:
    return _registry().metadata()


# ------------------------------------------------------------------ tasks
@app.post("/tasks", response_model=TaskOut)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskOut:
    # start_task branches on the provider: static planning for mock,
    # the agentic tool-calling loop for Groq.
    task = executor.start_task(
        db, payload.command, payload.idempotency_key, _registry(), get_settings(),
        auto_approve=payload.auto_approve,
    )
    return executor.task_out(task)


@app.get("/tasks", response_model=list[TaskOut])
def list_tasks(limit: int = Query(default=20, le=100), db: Session = Depends(get_db)) -> list[TaskOut]:
    tasks = db.query(Task).order_by(Task.created_at.desc()).limit(limit).all()
    return [executor.task_out(t) for t in tasks]


@app.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)) -> TaskOut:
    try:
        return executor.task_out(executor._get_task(db, task_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/tasks/{task_id}/approve", response_model=TaskOut)
def approve_task(task_id: str, payload: ApprovalRequest, db: Session = Depends(get_db)) -> TaskOut:
    try:
        return executor.task_out(executor.approve_task(db, task_id, payload.action_ids))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/tasks/{task_id}/reject", response_model=TaskOut)
def reject_task(task_id: str, payload: ApprovalRequest, db: Session = Depends(get_db)) -> TaskOut:
    try:
        return executor.task_out(executor.reject_task(db, task_id, payload.action_ids))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/tasks/{task_id}/run", response_model=TaskOut)
def run_task(task_id: str, db: Session = Depends(get_db)) -> TaskOut:
    try:
        task = executor._get_task(db, task_id)
        if task.agent_state_json and json.loads(task.agent_state_json).get("provider") != "local":
            # Agentic-loop task: resume the loop (runs newly-approved actions,
            # feeds results back to the model, continues reasoning).
            from .ai.planner import get_provider

            provider = get_provider(get_settings())
            return executor.task_out(
                executor.continue_agent_task(db, task_id, _registry(), provider, get_settings())
            )
        return executor.task_out(executor.run_task(db, task_id, _registry(), get_settings()))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel_task(task_id: str, db: Session = Depends(get_db)) -> TaskOut:
    try:
        return executor.task_out(executor.cancel_task(db, task_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# Re-export for tests that import from app.main
__all__ = ["app", "ActionOut"]


@app.post("/tasks/{task_id}/reply", response_model=TaskOut)
def reply_task(task_id: str, payload: TaskReply, db: Session = Depends(get_db)) -> TaskOut:
    """Bind conversational approval to the precise task the user is viewing."""
    try:
        task = executor._get_task(db, task_id)
        if task.status not in {"awaiting_approval", "awaiting_input"}:
            raise ValueError("This task is no longer waiting for a reply. Refresh before responding.")
        message = payload.message.strip().casefold().rstrip(".!۔।؟?").strip()
        yes = {"yes", "yes do it", "yes please", "confirm", "approve", "do it", "okay", "ok", "haan", "han", "haan kar do", "ji haan", "हाँ", "हां", "हाँ कर दो", "हां कर दो", "जी हाँ कर दो", "ہاں", "جی ہاں", "ہاں کر دو", "جی ہاں کر دو"}
        no = {"no", "cancel", "cancel it", "stop", "don't", "do not", "nahi", "nahin", "nahi karo", "नहीं", "नहीं करो", "रहने दो", "نہیں", "نہیں کرو", "رہنے دو"}
        if message in yes and task.status == "awaiting_approval":
            executor.approve_task(db, task_id)
            return run_task(task_id, db)
        if message in no:
            return executor.task_out(executor.cancel_task(db, task_id))
        # A clear new local command supersedes an unanswered clarification.
        # Do not reinterpret 'mute PC' as a missing folder path.
        from .ai.local_commands import local_plan
        from .ai.browser_commands import browser_plan
        from .ai.window_commands import close_request
        from .ai.command_intents import canonical_command
        routed = canonical_command(payload.message)
        explicit = local_plan(routed) or browser_plan(routed)
        if (explicit is not None and explicit.actions) or close_request(routed) is not None:
            executor.cancel_task(db, task_id)
            return executor.task_out(executor.start_task(db, payload.message, None, _registry(), get_settings()))
        if task.status == "awaiting_input" or (task.agent_state_json and json.loads(task.agent_state_json).get("provider") == "local"):
            from .orchestration.local_agent import correction_plan
            corrected = executor.create_task(db, payload.message)
            plan = correction_plan(corrected, task, payload.message, _registry())
            if plan is not None:
                executor.cancel_task(db, task_id)
                corrected.agent_state_json = corrected.agent_state_json or json.dumps({"provider": "local"})
                corrected = executor.plan_task(db, corrected, _registry(), get_settings(), preplanned=plan)
                if corrected.status == TaskStatus.APPROVED:
                    corrected = executor.run_task(db, corrected.id, _registry(), get_settings())
                return executor.task_out(corrected)
            # Remove the unused placeholder before normal conversational processing.
            db.delete(corrected)
            db.commit()
        if task.status == "awaiting_input":
            return executor.task_out(executor.start_task(db, payload.message, None, _registry(), get_settings()))
        # An unresolved correction must not be wrapped as a new prose command.
        # Keep the proposal waiting so a later exact path can still correct it.
        task.plan_note = 'Correction clear nahi hui. Sahi target ka exact path ya poori nayi command batayein; purana action execute nahi hua.'
        db.commit()
        return executor.task_out(task)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# Register LAST so API routes retain priority over the frontend file server.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
browser_extension = Path(__file__).resolve().parents[2] / "browser-extension"
if browser_extension.is_dir():
    app.mount("/browser-extension", StaticFiles(directory=str(browser_extension), html=True), name="browser-extension")
if (frontend_dist / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
