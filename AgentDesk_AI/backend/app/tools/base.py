"""Base classes for AgentDesk AI tools.

Every tool the AI can invoke is a BaseTool subclass with:
- a JSON input schema (Pydantic),
- a risk level driving the permission policy,
- execution logic, and
- verification logic.

The AI NEVER runs arbitrary code: it only picks a registered tool name and
arguments, which are validated here independently of the model.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Type

from pydantic import BaseModel


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolResult(BaseModel):
    success: bool
    output: dict[str, Any] = {}
    error: str | None = None


class Verification(BaseModel):
    passed: bool
    checks: list[str] = []
    details: str | None = None


@dataclass
class ToolContext:
    """Runtime context handed to every tool."""

    allowed_directories: list[Path] = field(default_factory=list)
    approved_applications: list[str] = field(default_factory=list)
    test_dir: Path = field(default_factory=lambda: Path("./agentdesk_test").resolve())
    discovery_directories: list[Path] = field(default_factory=list)
    isolate_system_controls: bool = False

    @classmethod
    def from_settings(cls) -> "ToolContext":
        from ..config import get_settings

        settings = get_settings()
        return cls(
            allowed_directories=settings.resolved_allowed_directories(),
            approved_applications=settings.resolved_approved_applications(),
            test_dir=Path(settings.test_dir).expanduser().resolve(),
            discovery_directories=settings.resolved_discovery_directories(),
            isolate_system_controls=True,
        )


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    args_schema: Type[BaseModel] = BaseModel

    def __init__(self, ctx: ToolContext | None = None) -> None:
        self.ctx = ctx or ToolContext.from_settings()

    @property
    def requires_approval(self) -> bool:
        return self.risk_for_args(None) != RiskLevel.LOW

    def risk_for_args(self, args: BaseModel | None) -> RiskLevel:
        """Risk may depend on arguments (e.g. approved vs unapproved app)."""
        return self.risk_level

    def validate_args(self, raw: dict[str, Any]) -> BaseModel:
        return self.args_schema.model_validate(raw)

    @abstractmethod
    def execute(self, args: BaseModel) -> ToolResult:
        """Perform the action. Must be honest: report real outcomes only."""

    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        if not result.success:
            return Verification(passed=False, checks=[], details="tool reported failure")
        return Verification(passed=True, checks=["tool reported success"])

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk_level.value,
            "requires_approval": self.risk_level != RiskLevel.LOW,
            "args_schema": self.args_schema.model_json_schema(),
        }
