"""Tests for path safety: normalization, traversal protection, allowed dirs."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.security.paths import PathNotAllowedError, is_allowed_root, resolve_within_allowed


def test_absolute_path_inside_allowed(tmp_path: Path):
    allowed = [tmp_path]
    target = tmp_path / "docs" / "file.txt"
    assert resolve_within_allowed(str(target), allowed) == target


def test_traversal_outside_allowed_is_blocked(tmp_path: Path):
    allowed = [tmp_path / "sandbox"]
    (tmp_path / "sandbox").mkdir()
    evil = tmp_path / "sandbox" / ".." / ".." / "etc" / "passwd"
    with pytest.raises(PathNotAllowedError):
        resolve_within_allowed(str(evil), allowed)


def test_relative_paths_rejected(tmp_path: Path):
    with pytest.raises(PathNotAllowedError):
        resolve_within_allowed("some/relative/path", [tmp_path])


def test_dotdot_inside_allowed_still_ok(tmp_path: Path):
    allowed = [tmp_path]
    p = tmp_path / "a" / ".." / "b.txt"
    assert resolve_within_allowed(str(p), allowed) == tmp_path / "b.txt"


def test_allowed_root_itself_ok(tmp_path: Path):
    assert resolve_within_allowed(str(tmp_path), [tmp_path]) == tmp_path


def test_is_allowed_root(tmp_path: Path):
    assert is_allowed_root(tmp_path, [tmp_path])
    assert not is_allowed_root(tmp_path / "sub", [tmp_path])


def test_home_expansion(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    allowed = [tmp_path]
    assert resolve_within_allowed("~/notes", allowed) == tmp_path / "notes"
