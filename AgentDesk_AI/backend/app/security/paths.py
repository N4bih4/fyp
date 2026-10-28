"""Path safety: normalization, allowed-directory enforcement, traversal protection."""
from __future__ import annotations

from pathlib import Path


class PathNotAllowedError(ValueError):
    """Raised when a path is rejected by the security policy."""


def resolve_within_allowed(raw_path: str, allowed: list[Path]) -> Path:
    """Resolve a user/AI-supplied path and ensure it stays inside allowed dirs.

    - Only absolute paths are accepted (relative paths are ambiguous).
    - The path is fully resolved (symlinks, `..`, `.`) before checking.
    - The resolved path must equal, or be contained in, an allowed directory.
    """
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        raise PathNotAllowedError(
            f"Only absolute paths are accepted (got {raw_path!r}). "
            "Ask the planner for an absolute path inside an allowed directory."
        )
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise PathNotAllowedError(f"Cannot resolve path {raw_path!r}: {exc}") from exc

    for base in allowed:
        try:
            base_resolved = base.expanduser().resolve()
        except OSError:
            continue
        if resolved == base_resolved or base_resolved in resolved.parents:
            return resolved
    raise PathNotAllowedError(
        f"Path {raw_path!r} is outside the allowed directories. "
        "Configure AGENTDESK_ALLOWED_DIRECTORIES to permit it."
    )


def is_allowed_root(path: Path, allowed: list[Path]) -> bool:
    """True if path IS one of the allowed roots (never delete these)."""
    resolved = path.resolve()
    return any(resolved == base.expanduser().resolve() for base in allowed)


# File types the OS runs (or hands to an interpreter) when "opened". The
# assistant must never open or author these: write + open would be arbitrary
# code execution by the LLM.
EXECUTABLE_EXTENSIONS = frozenset({
    ".exe", ".com", ".scr", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".msi", ".msp", ".lnk", ".url", ".reg", ".hta", ".cpl", ".jar", ".py", ".pyw", ".pif", ".gadget", ".appx", ".msix",
})


def is_executable_path(path: str | Path) -> bool:
    return Path(str(path)).suffix.lower() in EXECUTABLE_EXTENSIONS
