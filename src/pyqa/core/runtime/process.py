# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Safe wrappers around ``subprocess`` execution."""

from __future__ import annotations

import shutil

# Bandit: subprocess usage is intentional—we provide a controlled wrapper around
# external tool execution, normalising arguments and disabling ``shell=True``.
import subprocess  # nosec B404 suppression_valid: The subprocess module is standard library code and the wrapper enforces safe, shell-free invocation semantics.
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

CommandOverrideValue = Path | Mapping[str, str] | bool | float | int | None
CommandOverrideMapping = Mapping[str, CommandOverrideValue]

if TYPE_CHECKING:
    # Bandit: type-only import of subprocess metadata is part of the safe wrapper.
    from subprocess import (
        CompletedProcess as _CompletedProcess,  # nosec B404 suppression_valid: Type-checking requires the CompletedProcess alias even though it is never executed at runtime.
    )


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

    def with_overrides(self, overrides: CommandOverrideMapping) -> CommandOptions:
        """Return a new options instance with ``overrides`` applied.

        Args:
            overrides: Mapping of option names to replacement values.

        Returns:
            CommandOptions: Updated options instance with overrides applied.

        Raises:
            TypeError: If ``overrides`` includes an unknown option name or a value
                with an incompatible type.
            ValueError: When a timeout override is negative.
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
        cwd = self.cwd if "cwd" not in overrides else self._coerce_cwd_override(overrides["cwd"])
        env = self.env if "env" not in overrides else self._coerce_env_override(overrides["env"])
        check = self.check if "check" not in overrides else self._coerce_bool_override(overrides["check"], "check")
        capture_output = (
            self.capture_output
            if "capture_output" not in overrides
            else self._coerce_bool_override(overrides["capture_output"], "capture_output")
        )
        text = self.text if "text" not in overrides else self._coerce_bool_override(overrides["text"], "text")
        timeout = self.timeout if "timeout" not in overrides else self._coerce_timeout_override(overrides["timeout"])
        discard_stdin = (
            self.discard_stdin
            if "discard_stdin" not in overrides
            else self._coerce_bool_override(overrides["discard_stdin"], "discard_stdin")
        )
        return CommandOptions(
            cwd=cwd,
            env=env,
            check=check,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            discard_stdin=discard_stdin,
        )

    @staticmethod
    def _coerce_cwd_override(value: CommandOverrideValue) -> Path | None:
        """Return a validated override for ``cwd``.

        Args:
            value: Override candidate provided by the caller.

        Returns:
            Path | None: Normalised working directory override.

        Raises:
            TypeError: If ``value`` is neither ``None`` nor a :class:`pathlib.Path`.
        """

        if value is None or isinstance(value, Path):
            return value
        raise TypeError("cwd override must be a pathlib.Path or None")

    @staticmethod
    def _coerce_env_override(value: CommandOverrideValue) -> Mapping[str, str] | None:
        """Return a validated override for ``env``.

        Args:
            value: Override candidate supplied for the environment mapping.

        Returns:
            Mapping[str, str] | None: Validated environment overrides.

        Raises:
            TypeError: If the override is not a mapping of string keys to string values.
        """

        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise TypeError("env override must be a mapping of strings to strings")
        validated: dict[str, str] = {}
        for key, entry in value.items():
            if not isinstance(key, str) or not isinstance(entry, str):
                raise TypeError("env override must map strings to strings")
            validated[key] = entry
        return validated

    @staticmethod
    def _coerce_bool_override(value: CommandOverrideValue, option: str) -> bool:
        """Return a validated bool override for ``option``.

        Args:
            value: Override candidate extracted from the overrides mapping.
            option: Option name used when constructing error messages.

        Returns:
            bool: Validated boolean override.

        Raises:
            TypeError: If the override is not a boolean value.
        """

        if isinstance(value, bool):
            return value
        raise TypeError(f"{option} override must be a boolean value")

    @staticmethod
    def _coerce_timeout_override(value: CommandOverrideValue) -> float | None:
        """Return a validated timeout override.

        Args:
            value: Override candidate for the timeout value.

        Returns:
            float | None: Normalised timeout value in seconds.

        Raises:
            TypeError: If the override is not numeric.
            ValueError: When the override is negative.
        """

        if value is None:
            return None
        if isinstance(value, (int, float)):
            coerced = float(value)
            if coerced < 0:
                raise ValueError("timeout override must be non-negative")
            return coerced
        raise TypeError("timeout override must be a number or None")


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
    overrides: CommandOverrideMapping | None = None,
) -> _CompletedProcess[str]:
    """Execute ``args`` after normalising the executable path.

    Args:
        args: Command and argument sequence to execute.
        options: Base options configuring execution semantics.
        overrides: Keyword overrides applied to a cloned ``options`` instance.

    Returns:
        CompletedProcess: Subprocess execution metadata.

    Raises:
        FileNotFoundError: If the executable cannot be resolved on ``PATH``.
        SubprocessExecutionError: When ``check`` is true and the process exits
            with a non-zero status.
        TypeError: If an unknown override key is supplied.
    """

    normalized = _normalize_args(args)
    overrides_mapping: CommandOverrideMapping = overrides or {}
    resolved_options = (options or CommandOptions()).with_overrides(overrides_mapping)

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
