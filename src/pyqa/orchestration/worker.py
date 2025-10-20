# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Execution helpers for invoking external commands in a controlled manner."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from shutil import which as _which
from subprocess import CompletedProcess
from typing import Final

from ..core.runtime.process import (
    CommandOptionKey,
    CommandOptions,
    CommandOverrideMapping,
    CommandOverrideValue,
)
from ..core.runtime.process import run_command as _run_command

ENV_OVERRIDE_KEY: Final[CommandOptionKey] = "env"
CWD_OVERRIDE_KEY: Final[CommandOptionKey] = "cwd"
TIMEOUT_OVERRIDE_KEY: Final[CommandOptionKey] = "timeout"
CHECK_OVERRIDE_KEY: Final[CommandOptionKey] = "check"
CAPTURE_OUTPUT_OVERRIDE_KEY: Final[CommandOptionKey] = "capture_output"
DISCARD_STDIN_OVERRIDE_KEY: Final[CommandOptionKey] = "discard_stdin"


def find_executable(cmd: str) -> str | None:
    """Return the fully-qualified path to ``cmd`` if it exists on ``PATH``.

    Args:
        cmd: Executable name to resolve.

    Returns:
        str | None: Absolute path to the executable, or ``None`` when not found.
    """

    return _which(cmd)


def run_command(
    cmd: Sequence[str],
    *,
    options: CommandOptions | None = None,
    overrides: CommandOverrideMapping | None = None,
) -> CompletedProcess[str]:
    """Run ``cmd`` using hardened defaults and optional overrides.

    Args:
        cmd: Command arguments where the first item is the executable.
        options: Baseline command options applied prior to overrides.
        overrides: Optional mapping of option overrides such as ``env``.

    Returns:
        CompletedProcess[str]: Completed process with stdout and stderr captured.

    Raises:
        TypeError: If an environment override is supplied without a mapping.
    """

    resolved_options = options or CommandOptions()
    override_values: dict[CommandOptionKey, CommandOverrideValue] = dict(overrides or {})
    merged_env: Mapping[str, str] | None = resolved_options.env
    if ENV_OVERRIDE_KEY in override_values and override_values[ENV_OVERRIDE_KEY] is not None:
        override_env = override_values[ENV_OVERRIDE_KEY]
        if not isinstance(override_env, Mapping):
            raise TypeError("env override must be a mapping of environment variables")
        merged_env = dict(os.environ)
        merged_env.update({str(key): str(value) for key, value in override_env.items()})

    overrides_payload: dict[CommandOptionKey, CommandOverrideValue] = {
        CWD_OVERRIDE_KEY: override_values.get(CWD_OVERRIDE_KEY, resolved_options.cwd),
        ENV_OVERRIDE_KEY: merged_env,
        TIMEOUT_OVERRIDE_KEY: override_values.get(TIMEOUT_OVERRIDE_KEY, resolved_options.timeout),
        CHECK_OVERRIDE_KEY: False,
        CAPTURE_OUTPUT_OVERRIDE_KEY: True,
        DISCARD_STDIN_OVERRIDE_KEY: True,
    }
    effective_options = resolved_options.with_overrides(overrides_payload)
    return _run_command(cmd, options=effective_options)
