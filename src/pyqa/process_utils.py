# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Safe wrappers around ``subprocess`` execution."""

from __future__ import annotations

import shutil

# Bandit: subprocess usage is intentional—we provide a controlled wrapper around
# external tool execution, normalising arguments and disabling ``shell=True``.
import subprocess  # nosec B404
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Bandit: type-only import of subprocess metadata is part of the safe wrapper.
    from subprocess import CompletedProcess as _CompletedProcess  # nosec B404


class SubprocessExecutionError(RuntimeError):
    """Raised when a subprocess exits with a non-zero status while ``check`` is true."""

    def __init__(
        self,
        command: Sequence[str],
        returncode: int,
        stdout: str | None,
        stderr: str | None,
    ) -> None:
        super().__init__(
            f"Command '{command[0]}' exited with status {returncode}. stderr: {stderr or '<none>'}",
        )
        self.command = tuple(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _normalize_args(args: Sequence[str]) -> list[str]:
    if not args:
        msg = "subprocess command requires at least one argument"
        raise ValueError(msg)

    head, *rest = args
    head_path = Path(head)
    if head_path.is_absolute():
        return [str(head_path), *rest]

    resolved = shutil.which(head)
    if resolved is None:
        msg = f"Executable '{head}' was not found on PATH"
        raise FileNotFoundError(msg)
    return [resolved, *rest]


def run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
    capture_output: bool = False,
    text: bool = True,
    timeout: float | None = None,
    discard_stdin: bool = False,
) -> _CompletedProcess[str]:
    """Execute *args* after normalising the executable path."""
    normalized = _normalize_args(args)

    def _ensure_text(value: str | bytes | None) -> str | None:
        if value is None or isinstance(value, str):
            return value
        return value.decode(errors="ignore")

    try:
        # Bandit: commands originate from vetted tool configurations; we pass
        # argument lists directly without shell expansion.
        completed: _CompletedProcess[str] = subprocess.run(  # nosec B603
            normalized,
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            check=False,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            stdin=subprocess.DEVNULL if discard_stdin else None,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _ensure_text(exc.stdout) or ""
        stderr = _ensure_text(exc.stderr)
        timeout_msg = (
            f"Command timed out after {timeout:.1f}s"
            if timeout is not None
            else "Command timed out"
        )
        combined_stderr = f"{stderr}\n{timeout_msg}" if stderr else timeout_msg
        completed = subprocess.CompletedProcess(
            args=(list(exc.cmd) if isinstance(exc.cmd, (list, tuple)) else list(normalized)),
            returncode=124,
            stdout=stdout,
            stderr=combined_stderr,
        )

    if check and completed.returncode != 0:
        raise SubprocessExecutionError(
            normalized,
            completed.returncode,
            completed.stdout if isinstance(completed.stdout, str) else None,
            completed.stderr if isinstance(completed.stderr, str) else None,
        )

    return completed


__all__ = ["SubprocessExecutionError", "run_command"]
