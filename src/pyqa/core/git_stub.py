# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Provide a lightweight git shim for environments lacking git."""

from __future__ import annotations

import base64
import binascii
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

GIT_EXECUTABLE: Final[str] = "git"
GIT_METADATA_DIR: Final[str] = ".git"
CURRENT_DIRECTORY_SENTINEL: Final[str] = "."
STATUS_DELETED_PREFIX: Final[str] = " D "
STATUS_MODIFIED_PREFIX: Final[str] = " M "
STATUS_UNTRACKED_PREFIX: Final[str] = "?? "
DIFF_CACHED_FLAG: Final[str] = "--cached"
LSFILES_OTHERS_FLAG: Final[str] = "--others"
STATE_FILENAME: Final[str] = "pyqa_stub_state.json"
_ORIGINAL_RUN = subprocess.run
_ORIGINAL_WHICH = shutil.which


@dataclass(slots=True)
class _RepositoryState:
    """Maintain tracked and staged data for the stub repository."""

    tracked: dict[str, str]
    staged: dict[str, str | None]

    @classmethod
    def load(cls, root: Path) -> _RepositoryState:
        """Load repository state from disk or return an empty default.

        Args:
            root: Repository root directory containing stub metadata.

        Returns:
            _RepositoryState: Loaded repository state instance.
        """

        state_file = root / GIT_METADATA_DIR / STATE_FILENAME
        if not state_file.exists():
            return cls(tracked={}, staged={})
        raw = json.loads(state_file.read_text(encoding="utf-8"))
        return cls(tracked=dict(raw.get("tracked", {})), staged=dict(raw.get("staged", {})))

    def save(self, root: Path) -> None:
        """Persist the current repository state to disk.

        Args:
            root: Repository root directory containing stub metadata.
        """

        state_file = root / ".git" / STATE_FILENAME
        state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"tracked": self.tracked, "staged": self.staged}
        state_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _encode_bytes(data: bytes) -> str:
    """Encode ``data`` to a Base64 string.

    Args:
        data: Raw bytes to encode.

    Returns:
        str: Base64 encoded representation of ``data``.
    """

    return base64.b64encode(data).decode("ascii")


def _decode_bytes(data: str) -> bytes:
    """Decode a Base64 string into bytes.

    Args:
        data: Base64 encoded string.

    Returns:
        bytes: Decoded byte sequence.
    """

    return base64.b64decode(data.encode("ascii"))


def _repo_root(cwd: Path) -> Path:
    """Return the repository root for the stub (identical to ``cwd``).

    Args:
        cwd: Working directory requested by the caller.

    Returns:
        Path: Repository root directory.
    """

    return cwd


def _init_repo(cwd: Path) -> tuple[int, str, str]:
    """Initialise the stub repository metadata under ``cwd``.

    Args:
        cwd: Repository root directory.

    Returns:
        tuple[int, str, str]: Return code, stdout, and stderr values.
    """

    git_dir = cwd / GIT_METADATA_DIR
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    _RepositoryState(tracked={}, staged={}).save(cwd)
    return 0, "", ""


def _collect_paths(cwd: Path, arguments: Sequence[str]) -> list[Path]:
    """Collect file paths referenced by ``arguments`` relative to ``cwd``.

    Args:
        cwd: Repository root directory.
        arguments: Paths provided to the stub command.

    Returns:
        list[Path]: File paths that match the requested arguments.
    """

    paths: list[Path] = []
    if not arguments:
        return paths
    for arg in arguments:
        target = (cwd / arg).resolve()
        if target.is_dir():
            paths.extend(path for path in target.rglob("*") if path.is_file() and GIT_METADATA_DIR not in path.parts)
        elif target.is_file():
            paths.append(target)
    return paths


def _git_add(cwd: Path, args: Sequence[str]) -> tuple[int, str, str]:
    """Stage paths referenced in ``args`` inside ``cwd``.

    Args:
        cwd: Repository root directory.
        args: Paths (relative or glob) to stage.

    Returns:
        tuple[int, str, str]: Return code, stdout, and stderr values.
    """

    state = _RepositoryState.load(cwd)
    if CURRENT_DIRECTORY_SENTINEL in args or not args:
        paths = [path for path in cwd.rglob("*") if path.is_file() and GIT_METADATA_DIR not in path.parts]
    else:
        paths = _collect_paths(cwd, args)
    for path in paths:
        rel = path.relative_to(cwd).as_posix()
        state.staged[rel] = _encode_bytes(path.read_bytes())
    state.save(cwd)
    return 0, "", ""


def _git_commit(cwd: Path) -> tuple[int, str, str]:
    """Commit staged changes for the repository rooted at ``cwd``.

    Args:
        cwd: Repository root directory.

    Returns:
        tuple[int, str, str]: Return code, stdout, and stderr values.
    """

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
    """Retrieve tracked bytes for ``rel`` or ``None`` when absent.

    Args:
        state: Repository state containing tracked entries.
        rel: Relative path to inspect.

    Returns:
        bytes | None: Tracked bytes when present; otherwise ``None``.
    """

    encoded = state.tracked.get(rel)
    if encoded is None:
        return None
    try:
        return _decode_bytes(encoded)
    except binascii.Error:
        return None


def _working_bytes(root: Path, rel: str) -> bytes | None:
    """Retrieve working-tree bytes for ``rel`` located under ``root``.

    Args:
        root: Repository root directory.
        rel: Relative path to inspect.

    Returns:
        bytes | None: Current working-tree bytes; ``None`` when unavailable.
    """

    candidate = root / rel
    if not candidate.exists():
        return None
    try:
        return candidate.read_bytes()
    except OSError:
        return None


def _git_status(cwd: Path) -> tuple[int, str, str]:
    """Generate git-status style output for the repository rooted at ``cwd``.

    Args:
        cwd: Repository root directory.

    Returns:
        tuple[int, str, str]: Return code, stdout, and stderr values.
    """

    state = _RepositoryState.load(cwd)
    lines: list[str] = []

    for rel in sorted(state.tracked):
        tracked_bytes = _tracked_bytes(state, rel)
        working_bytes = _working_bytes(cwd, rel)
        if working_bytes is None:
            lines.append(f"{STATUS_DELETED_PREFIX}{rel}")
        elif tracked_bytes != working_bytes:
            lines.append(f"{STATUS_MODIFIED_PREFIX}{rel}")

    tracked_set = set(state.tracked)
    for path in cwd.rglob("*"):
        if not path.is_file():
            continue
        if GIT_METADATA_DIR in path.parts:
            continue
        rel = path.relative_to(cwd).as_posix()
        if rel not in tracked_set:
            lines.append(f"{STATUS_UNTRACKED_PREFIX}{rel}")

    return 0, "\n".join(lines), ""


def _diff_tracked(cwd: Path, state: _RepositoryState) -> list[str]:
    """Collect tracked files whose content differs from the working tree.

    Args:
        cwd: Repository root directory.
        state: Repository state containing tracked entries.

    Returns:
        list[str]: Relative paths whose content differs from the tracked data.
    """

    results: list[str] = []
    for rel in sorted(state.tracked):
        tracked_bytes = _tracked_bytes(state, rel)
        working_bytes = _working_bytes(cwd, rel)
        if tracked_bytes != working_bytes:
            results.append(rel)
    return results


def _git_diff(cwd: Path, args: Sequence[str]) -> tuple[int, str, str]:
    """Generate git-diff style output for ``cwd`` respecting ``args``.

    Args:
        cwd: Repository root directory.
        args: Diff arguments supplied by the caller.

    Returns:
        tuple[int, str, str]: Return code, stdout, and stderr values.
    """

    state = _RepositoryState.load(cwd)
    if "--cached" in args:
        paths = sorted(rel for rel, data in state.staged.items() if data is not None)
        return 0, "\n".join(paths), ""
    return 0, "\n".join(_diff_tracked(cwd, state)), ""


def _untracked_paths(cwd: Path, state: _RepositoryState) -> list[str]:
    """Collect untracked paths for the repository rooted at ``cwd``.

    Args:
        cwd: Repository root directory.
        state: Current repository state object.

    Returns:
        list[str]: Relative paths that are not tracked.
    """

    tracked_set = set(state.tracked)
    results: list[str] = []
    for path in cwd.rglob("*"):
        if not path.is_file():
            continue
        if GIT_METADATA_DIR in path.parts:
            continue
        rel = path.relative_to(cwd).as_posix()
        if rel not in tracked_set:
            results.append(rel)
    return results


def _git_ls_files(cwd: Path, args: Sequence[str]) -> tuple[int, str, str]:
    """Generate git-ls-files style output for the repository rooted at ``cwd``.

    Args:
        cwd: Repository root directory.
        args: Command arguments supplied by the caller.

    Returns:
        tuple[int, str, str]: Return code, stdout, and stderr values.
    """

    state = _RepositoryState.load(cwd)
    if "--others" in args:
        return 0, "\n".join(_untracked_paths(cwd, state)), ""
    return 0, "\n".join(sorted(state.tracked)), ""


def _handle_git_command(cmd: Sequence[str], cwd: Path) -> tuple[int, str, str]:
    """Dispatch git subcommands implemented by the stub.

    Args:
        cmd: Git command arguments excluding the ``git`` executable.
        cwd: Repository root directory.

    Returns:
        tuple[int, str, str]: Return code, stdout, and stderr values.
    """

    if not cmd:
        return 1, "", "missing git subcommand"

    command, *args = cmd
    handlers: dict[str, Callable[[Sequence[str], Path], tuple[int, str, str]]] = {
        "init": lambda _args, repo: _init_repo(repo),
        "config": lambda _args, _repo: (0, "", ""),
        "add": lambda cmd_args, repo: _git_add(repo, cmd_args),
        "commit": lambda _args, repo: _git_commit(repo),
        "status": lambda _args, repo: _git_status(repo),
        "diff": lambda cmd_args, repo: _git_diff(repo, cmd_args),
        "ls-files": lambda cmd_args, repo: _git_ls_files(repo, cmd_args),
        "merge-base": lambda _args, _repo: (0, "", ""),
        "rev-parse": lambda _args, _repo: (0, "HEAD\n", ""),
    }
    handler = handlers.get(command)
    if handler is None:
        return 0, "", ""
    return handler(args, cwd)


def _git_stub_run(
    args: Sequence[str] | str,
    *pos_args: Any,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    """Emulate ``subprocess.run`` for git commands when git is unavailable.

    Args:
        args: Command sequence or shell string to execute.
        *pos_args: Positional arguments forwarded to the original runner.
        **kwargs: Keyword arguments forwarded to the original runner.

    Returns:
        subprocess.CompletedProcess[Any]: Completed process describing the outcome.
    """

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

    if shutil.which(GIT_EXECUTABLE):
        return
    if getattr(subprocess, "_pyqa_git_stub_installed", False):
        return
    subprocess.run = _git_stub_run  # type: ignore[assignment]
    shutil.which = lambda cmd, *args, **kwargs: (
        GIT_EXECUTABLE if cmd == GIT_EXECUTABLE else _ORIGINAL_WHICH(cmd, *args, **kwargs)  # type: ignore[assignment]
    )
    subprocess._pyqa_git_stub_installed = True
