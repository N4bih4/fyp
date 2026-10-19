"""Permission policy: risk categories and approval requirements."""
from __future__ import annotations

from ..tools.base import RiskLevel

RISK_DESCRIPTIONS = {
    RiskLevel.LOW: "Low risk: opening approved applications and folders, listing contents.",
    RiskLevel.MEDIUM: "Medium risk: creating, moving, renaming, compressing files. Needs confirmation.",
    RiskLevel.HIGH: "High risk: deleting data, overwriting, unapproved apps. Needs explicit approval.",
}


def needs_approval(risk: RiskLevel) -> bool:
    """Medium and high risk actions require user approval before execution."""
    return risk in (RiskLevel.MEDIUM, RiskLevel.HIGH)


def needs_explicit_approval(risk: RiskLevel) -> bool:
    """High risk actions require explicit (not just default) approval."""
    return risk == RiskLevel.HIGH


def approval_prompt(risk: RiskLevel, tool_name: str) -> str:
    if risk == RiskLevel.HIGH:
        return f"High-risk action '{tool_name}' requires your explicit approval."
    if risk == RiskLevel.MEDIUM:
        return f"Action '{tool_name}' changes data. Please confirm to proceed."
    return f"Action '{tool_name}' is low risk and can run automatically."
