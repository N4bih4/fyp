"""Tests for the permission policy and risk classification."""
from __future__ import annotations

from app.security.permissions import (
    approval_prompt,
    needs_approval,
    needs_explicit_approval,
)
from app.tools.apps import OpenApplicationTool
from app.tools.base import RiskLevel, ToolContext
from app.tools.filesystem import CreateFolderTool, DeleteFileTool, ListFolderTool
from app.tools.system import TakeScreenshotTool


def test_risk_matrix():
    assert needs_approval(RiskLevel.LOW) is False
    assert needs_approval(RiskLevel.MEDIUM) is True
    assert needs_approval(RiskLevel.HIGH) is True
    assert needs_explicit_approval(RiskLevel.HIGH) is True
    assert needs_explicit_approval(RiskLevel.MEDIUM) is False


def test_tool_risk_levels(ctx: ToolContext):
    assert ListFolderTool(ctx).risk_level == RiskLevel.LOW
    assert CreateFolderTool(ctx).risk_level == RiskLevel.MEDIUM
    assert DeleteFileTool(ctx).risk_level == RiskLevel.HIGH
    assert TakeScreenshotTool(ctx).risk_level == RiskLevel.MEDIUM


def test_open_application_dynamic_risk(ctx: ToolContext):
    tool = OpenApplicationTool(ctx)  # ctx approves chrome + notepad
    assert tool.risk_for_args(tool.validate_args({"app_name": "Chrome"})) == RiskLevel.LOW
    assert tool.risk_for_args(tool.validate_args({"app_name": "unknown-app"})) == RiskLevel.HIGH


def test_approval_prompts_mention_risk():
    assert "explicit" in approval_prompt(RiskLevel.HIGH, "delete_file")
    assert "confirm" in approval_prompt(RiskLevel.MEDIUM, "create_folder")
