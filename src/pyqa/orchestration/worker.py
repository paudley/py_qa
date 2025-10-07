# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Execution helpers for invoking external commands in a controlled manner."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from shutil import which as _which
from subprocess import CompletedProcess
from typing import Final

from ..core.runtime.process import CommandOptions
from ..core.runtime.process import run_command as _run_command

ENV_OVERRIDE_KEY: Final[str] = "env"
CWD_OVERRIDE_KEY: Final[str] = "cwd"
TIMEOUT_OVERRIDE_KEY: Final[str] = "timeout"


def find_executable(cmd: str) -> str | None:
    """Locate an executable on ``PATH`` (virtualenv aware)."""
    return _which(cmd)


def run_command(
    cmd: Sequence[str],
    *,
    options: CommandOptions | None = None,
    **overrides: object,
) -> CompletedProcess[str]:
    """Run a command returning a completed process with text outputs."""
    resolved_options = options or CommandOptions()
    merged_env: Mapping[str, str] | None = resolved_options.env
    if ENV_OVERRIDE_KEY in overrides and overrides[ENV_OVERRIDE_KEY] is not None:
        override_env = overrides[ENV_OVERRIDE_KEY]
        if not isinstance(override_env, Mapping):
            raise TypeError("env override must be a mapping of environment variables")
        merged_env = dict(os.environ)
        merged_env.update({str(key): str(value) for key, value in override_env.items()})

    effective_options = resolved_options.with_overrides(
        {
            CWD_OVERRIDE_KEY: overrides.get(CWD_OVERRIDE_KEY, resolved_options.cwd),
            ENV_OVERRIDE_KEY: merged_env,
            TIMEOUT_OVERRIDE_KEY: overrides.get(TIMEOUT_OVERRIDE_KEY, resolved_options.timeout),
            "check": False,
            "capture_output": True,
            "discard_stdin": True,
        }
    )
    return _run_command(cmd, options=effective_options)
