# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Provide a lightweight git stub for environments lacking git."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

_STATE_FILENAME = "pyqa_stub_state.json"
_ORIGINAL_RUN = subprocess.run
_ORIGINAL_WHICH = shutil.which


@dataclass(slots=True)
class _RepositoryState:
    """Maintain tracked and staged data for the stub repository."""

    tracked: dict[str, str]
    staged: dict[str, str | None]

    @classmethod
    def load(cls, root: Path) -> "_RepositoryState":
        state_file = root / ".git" / _STATE_FILENAME
        if not state_file.exists():
            return cls(tracked={}, staged={})
        raw = json.loads(state_file.read_text(encoding="utf-8"))
        return cls(tracked=dict(raw.get("tracked", {})), staged=dict(raw.get("staged", {})))

    def save(self, root: Path) -> None:
        state_file = root / ".git" / _STATE_FILENAME
        state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"tracked": self.tracked, "staged": self.staged}
        state_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _encode_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode_bytes(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def _repo_root(cwd: Path) -> Path:
    return cwd


def _init_repo(cwd: Path) -> tuple[int, str, str]:
    git_dir = cwd / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    _RepositoryState(tracked={}, staged={}).save(cwd)
    return 0, "", ""


def _collect_paths(cwd: Path, arguments: Sequence[str]) -> Iterable[Path]:
    if not arguments:
        return []
    for arg in arguments:
        target = (cwd / arg).resolve()
        if target.is_dir():
            yield from (
                path
                for path in target.rglob("*")
                if path.is_file() and ".git" not in path.parts
            )
        elif target.is_file():
            yield target
    return []


def _git_add(cwd: Path, args: Sequence[str]) -> tuple[int, str, str]:
    state = _RepositoryState.load(cwd)
    if "." in args or not args:
        paths = [
            path
            for path in cwd.rglob("*")
            if path.is_file() and ".git" not in path.parts
        ]
    else:
        paths = list(_collect_paths(cwd, args))
    for path in paths:
        rel = path.relative_to(cwd).as_posix()
        state.staged[rel] = _encode_bytes(path.read_bytes())
    state.save(cwd)
    return 0, "", ""


def _git_commit(cwd: Path) -> tuple[int, str, str]:
    state = _RepositoryState.load(cwd)
    if not state.staged:
        return 0, "", ""
    for rel, encoded in state.staged.items():
        if encoded is None:
            state.tracked.pop(rel, None)
        else:
            state.tracked[rel] = encoded
    state.staged.clear()
    state.save(cwd)
    return 0, "", ""


def _tracked_bytes(state: _RepositoryState, rel: str) -> bytes | None:
    encoded = state.tracked.get(rel)
    if encoded is None:
        return None
    try:
        return _decode_bytes(encoded)
    except base64.binascii.Error:
        return None


def _working_bytes(root: Path, rel: str) -> bytes | None:
    candidate = root / rel
    if not candidate.exists():
        return None
    try:
        return candidate.read_bytes()
    except OSError:
        return None


def _git_status(cwd: Path) -> tuple[int, str, str]:
    state = _RepositoryState.load(cwd)
    lines: list[str] = []

    for rel in sorted(state.tracked):
        tracked_bytes = _tracked_bytes(state, rel)
        working_bytes = _working_bytes(cwd, rel)
        if working_bytes is None:
            lines.append(f" D {rel}")
        elif tracked_bytes != working_bytes:
            lines.append(f" M {rel}")

    tracked_set = set(state.tracked)
    for path in cwd.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        rel = path.relative_to(cwd).as_posix()
        if rel not in tracked_set:
            lines.append(f"?? {rel}")

    return 0, "\n".join(lines), ""


def _diff_tracked(cwd: Path, state: _RepositoryState) -> list[str]:
    results: list[str] = []
    for rel in sorted(state.tracked):
        tracked_bytes = _tracked_bytes(state, rel)
        working_bytes = _working_bytes(cwd, rel)
        if tracked_bytes != working_bytes:
            results.append(rel)
    return results


def _git_diff(cwd: Path, args: Sequence[str]) -> tuple[int, str, str]:
    state = _RepositoryState.load(cwd)
    if "--cached" in args:
        paths = sorted(rel for rel, data in state.staged.items() if data is not None)
        return 0, "\n".join(paths), ""
    return 0, "\n".join(_diff_tracked(cwd, state)), ""


def _untracked_paths(cwd: Path, state: _RepositoryState) -> list[str]:
    tracked_set = set(state.tracked)
    results: list[str] = []
    for path in cwd.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        rel = path.relative_to(cwd).as_posix()
        if rel not in tracked_set:
            results.append(rel)
    return results


def _git_ls_files(cwd: Path, args: Sequence[str]) -> tuple[int, str, str]:
    state = _RepositoryState.load(cwd)
    if "--others" in args:
        return 0, "\n".join(_untracked_paths(cwd, state)), ""
    return 0, "\n".join(sorted(state.tracked)), ""


def _handle_git_command(cmd: Sequence[str], cwd: Path) -> tuple[int, str, str]:
    if not cmd:
        return 1, "", "missing git subcommand"

    command, *args = cmd
    if command == "init":
        return _init_repo(cwd)
    if command == "config":
        return 0, "", ""
    if command == "add":
        return _git_add(cwd, args)
    if command == "commit":
        return _git_commit(cwd)
    if command == "status":
        return _git_status(cwd)
    if command == "diff":
        return _git_diff(cwd, args)
    if command == "ls-files":
        return _git_ls_files(cwd, args)
    if command == "merge-base":
        return 0, "", ""
    if command == "rev-parse":
        return 0, "HEAD\n", ""
    return 0, "", ""


def _git_stub_run(
    args: Sequence[str] | str,
    *pos_args: Any,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    if isinstance(args, str):
        if not args:
            return _ORIGINAL_RUN(args, *pos_args, **kwargs)
        cmd_list = args.split()
    else:
        cmd_list = list(args)

    if not cmd_list or cmd_list[0] != "git":
        return _ORIGINAL_RUN(args, *pos_args, **kwargs)

    cwd = Path(kwargs.get("cwd") or os.getcwd())
    return_code, stdout, stderr = _handle_git_command(cmd_list[1:], cwd)

    text_mode = kwargs.get("text") or kwargs.get("encoding") is not None
    stdout_data = stdout if text_mode else stdout.encode()
    stderr_data = stderr if text_mode else stderr.encode()

    completed = subprocess.CompletedProcess(cmd_list, return_code, stdout=stdout_data, stderr=stderr_data)

    check = kwargs.get("check", False)
    if check and return_code != 0:
        raise subprocess.CalledProcessError(return_code, cmd_list, output=stdout_data, stderr=stderr_data)

    return completed


def install_git_stub() -> None:
    """Install a git stub when the git executable is unavailable."""

    if shutil.which("git"):
        return
    if getattr(subprocess, "_pyqa_git_stub_installed", False):
        return
    subprocess.run = _git_stub_run  # type: ignore[assignment]
    shutil.which = lambda cmd, *args, **kwargs: ("git" if cmd == "git" else _ORIGINAL_WHICH(cmd, *args, **kwargs))  # type: ignore[assignment]
    subprocess._pyqa_git_stub_installed = True
