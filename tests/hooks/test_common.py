from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest

import _common
from helpers import Git


def test_fingerprint_is_stable_on_a_clean_tree(git_repo: Path) -> None:
    assert _common.tree_fingerprint(git_repo) == _common.tree_fingerprint(git_repo)


def test_fingerprint_changes_on_tracked_edit(git_repo: Path) -> None:
    clean = _common.tree_fingerprint(git_repo)
    (git_repo / "README.md").write_text("changed\n", encoding="utf-8")
    assert _common.tree_fingerprint(git_repo) != clean


def test_fingerprint_changes_on_staged_edit(git_repo: Path, git: Git) -> None:
    clean = _common.tree_fingerprint(git_repo)
    (git_repo / "README.md").write_text("staged\n", encoding="utf-8")
    unstaged = _common.tree_fingerprint(git_repo)
    git(git_repo, "add", "README.md")
    staged = _common.tree_fingerprint(git_repo)
    assert len({clean, unstaged, staged}) == 3


def test_fingerprint_tracks_untracked_file_content(git_repo: Path) -> None:
    clean = _common.tree_fingerprint(git_repo)
    new = git_repo / "new.py"
    new.write_text("a = 1\n", encoding="utf-8")
    first = _common.tree_fingerprint(git_repo)
    new.write_text("a = 2\n", encoding="utf-8")
    second = _common.tree_fingerprint(git_repo)
    assert len({clean, first, second}) == 3


def test_fingerprint_changes_after_commit(git_repo: Path, git: Git) -> None:
    clean = _common.tree_fingerprint(git_repo)
    git(git_repo, "commit", "-q", "--allow-empty", "-m", "chore: empty")
    assert _common.tree_fingerprint(git_repo) != clean


def test_fingerprint_ignores_gitignored_files_and_hook_state(git_repo: Path, git: Git) -> None:
    (git_repo / ".gitignore").write_text("*.log\n", encoding="utf-8")
    git(git_repo, "add", ".gitignore")
    git(git_repo, "commit", "-q", "-m", "chore: ignore")
    clean = _common.tree_fingerprint(git_repo)
    (git_repo / "debug.log").write_text("noise\n", encoding="utf-8")
    _common.save_state(git_repo, "session-x", {"baseline": "abc"})
    assert _common.tree_fingerprint(git_repo) == clean


def test_fingerprint_without_commits(tmp_path: Path, git: Git) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    assert len(_common.tree_fingerprint(tmp_path)) == 64


def test_fingerprint_outside_git(tmp_path: Path) -> None:
    assert _common.tree_fingerprint(tmp_path) == "nogit"


def test_state_roundtrip_and_corruption(tmp_path: Path) -> None:
    assert _common.load_state(tmp_path, "missing") == {}
    _common.save_state(tmp_path, "s", {"blocks": 2})
    assert _common.load_state(tmp_path, "s") == {"blocks": 2}
    _common.state_path(tmp_path, "s").write_text("{not json", encoding="utf-8")
    assert _common.load_state(tmp_path, "s") == {}
    _common.state_path(tmp_path, "s").write_text("[1, 2]", encoding="utf-8")
    assert _common.load_state(tmp_path, "s") == {}


def test_state_names_cannot_escape_the_state_dir(tmp_path: Path) -> None:
    path = _common.state_path(tmp_path, "../../evil/../x")
    assert path.parent == tmp_path / _common.STATE_DIR
    assert _common.state_path(tmp_path, "..").name == "default.json"


def test_prune_state_removes_old_sessions(tmp_path: Path) -> None:
    _common.save_state(tmp_path, "session-old", {})
    _common.save_state(tmp_path, "session-new", {})
    _common.save_state(tmp_path, "last-pass", {})
    old = _common.state_path(tmp_path, "session-old")
    stale = time.time() - 30 * 86400
    os.utime(old, (stale, stale))
    _common.prune_state(tmp_path)
    assert not old.exists()
    assert _common.state_path(tmp_path, "session-new").exists()
    assert _common.state_path(tmp_path, "last-pass").exists()


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "full"), ("", "full"), ("FAST", "fast"), (" off ", "off"), ("bogus", "full")],
)
def test_normalize_gate_mode(value: str | None, expected: str) -> None:
    assert _common.normalize_gate_mode(value) == expected


def test_read_payload() -> None:
    assert _common.read_payload(io.StringIO("")) == {}
    assert _common.read_payload(io.StringIO('{"a": 1}')) == {"a": 1}
    with pytest.raises(TypeError):
        _common.read_payload(io.StringIO("[]"))


def test_project_root_resolution(git_repo: Path, tmp_path: Path) -> None:
    sub = git_repo / "pkg"
    sub.mkdir()
    by_env = _common.project_root({"CLAUDE_PROJECT_DIR": str(sub)}, {})
    by_cwd = _common.project_root({}, {"cwd": str(sub)})
    assert by_env.resolve() == git_repo.resolve()
    assert by_cwd.resolve() == git_repo.resolve()
    outside = tmp_path / "plain"
    outside.mkdir()
    assert _common.project_root({"CLAUDE_PROJECT_DIR": str(outside)}, {}) == outside


def test_git_toplevel_walks_up_from_missing_paths(git_repo: Path) -> None:
    top = _common.git_toplevel(git_repo / "not" / "created" / "file.py")
    assert top is not None
    assert top.resolve() == git_repo.resolve()
