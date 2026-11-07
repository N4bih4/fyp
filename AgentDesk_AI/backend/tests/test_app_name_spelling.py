"""Speech recognisers write app names with hyphens, spaces and punctuation: "Anti-gravity," must still open Antigravity."""
from __future__ import annotations

import pytest

from app.tools.apps import OpenApplicationTool


@pytest.mark.parametrize("spoken,canonical", [
    ("Anti-gravity,", "antigravity"), ("anti-gravity", "antigravity"), ("Anti Gravity", "antigravity"), ("Antigravity.", "antigravity"),
    ("Code X", "codex"), ("codex", "codex"), ("Claude Code", "claude"), ("VS Code", "visual studio code"), ("Google Chrome", "chrome"),
    ("Notepad", "notepad"), ("Zoom", "zoom"),
])
def test_spoken_app_names_resolve(spoken, canonical):
    assert OpenApplicationTool._canonical_app_name(spoken) == canonical
