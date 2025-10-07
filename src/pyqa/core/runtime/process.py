# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Safe wrappers around ``subprocess`` execution."""

from __future__ import annotations

import shutil

# Bandit: subprocess usage is intentional—we provide a controlled wrapper around
# external tool execution, normalising arguments and disabling ``shell=True``.
import subprocess  # nosec B404 - standard library use, safe despite Bandit heuristic
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Bandit: type-only import of subprocess metadata is part of the safe wrapper.
    from subprocess import CompletedProcess as _CompletedProcess  # nosec B404 - standard library aliasing


@dataclass(slots=True)
class CommandOptions:
    """Immutable command execution options."""

    cwd: Path | None = None
    env: Mapping[str, str] | None = None
    check: bool = True
    capture_output: bool = False
    text: bool = True
    timeout: float | None = None
    discard_stdin: bool = False

    def with_overrides(self, overrides: Mapping[str, Any]) -> CommandOptions:
        """Return a new options instance with ``overrides`` applied.

        Args:
            overrides: Mapping of option names to replacement values.

        Returns:
            CommandOptions: Updated options instance with overrides applied.

        Raises:
            TypeError: If ``overrides`` includes an unknown option name.
        """

        valid_keys = {
            "cwd",
            "env",
            "check",
            "capture_output",
            "text",
            "timeout",
            "discard_stdin",
        }
        unknown = [key for key in overrides if key not in valid_keys]
        if unknown:
            message = ", ".join(sorted(unknown))
            raise TypeError(f"Unknown command option(s): {message}")
        return replace(self, **overrides)


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
    options: CommandOptions | None = None,
    **overrides: Any,
) -> _CompletedProcess[str]:
    """Execute ``args`` after normalising the executable path.

    Args:
        args: Command and argument sequence to execute.
        options: Base options configuring execution semantics.
        **overrides: Keyword overrides applied to a cloned ``options`` instance.

    Returns:
        CompletedProcess: Subprocess execution metadata.

    Raises:
        FileNotFoundError: If the executable cannot be resolved on ``PATH``.
        SubprocessExecutionError: When ``check`` is true and the process exits
            with a non-zero status.
        TypeError: If an unknown override key is supplied.
    """

    normalized = _normalize_args(args)
    resolved_options = (options or CommandOptions()).with_overrides(overrides)

    def _ensure_text(value: str | bytes | None) -> str | None:
        if value is None or isinstance(value, str):
            return value
        return value.decode(errors="ignore")

    try:
        # Bandit: commands originate from vetted tool configurations; we pass
        # argument lists directly without shell expansion.
        completed: _CompletedProcess[str] = subprocess.run(  # nosec B603 - controlled arguments, not user supplied
            normalized,
            cwd=str(resolved_options.cwd) if resolved_options.cwd is not None else None,
            env=dict(resolved_options.env) if resolved_options.env is not None else None,
            check=False,
            capture_output=resolved_options.capture_output,
            text=resolved_options.text,
            timeout=resolved_options.timeout,
            stdin=subprocess.DEVNULL if resolved_options.discard_stdin else None,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _ensure_text(exc.stdout) or ""
        stderr = _ensure_text(exc.stderr)
        timeout_value = resolved_options.timeout
        timeout_msg = (
            f"Command timed out after {timeout_value:.1f}s" if timeout_value is not None else "Command timed out"
        )
        combined_stderr = f"{stderr}\n{timeout_msg}" if stderr else timeout_msg
        completed = subprocess.CompletedProcess(
            args=(list(exc.cmd) if isinstance(exc.cmd, (list, tuple)) else list(normalized)),
            returncode=124,
            stdout=stdout,
            stderr=combined_stderr,
        )

    if resolved_options.check and completed.returncode != 0:
        raise SubprocessExecutionError(
            normalized,
            completed.returncode,
            completed.stdout if isinstance(completed.stdout, str) else None,
            completed.stderr if isinstance(completed.stderr, str) else None,
        )

    return completed


__all__ = ["SubprocessExecutionError", "run_command"]
