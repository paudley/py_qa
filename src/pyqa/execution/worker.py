# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Execution helpers for invoking external commands in a controlled manner."""

from __future__ import annotations

import os
from pathlib import Path
from shutil import which as _which
from typing import Mapping, Sequence

from ..process_utils import run_command as _run_command


def find_executable(cmd: str) -> str | None:
    """Locate an executable on ``PATH`` (virtualenv aware)."""

    return _which(cmd)


def run_command(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
):
    """Run a command returning a completed process with text outputs."""

    merged_env: dict[str, str] | None = None
    if env:
        merged_env = os.environ.copy()
        merged_env.update(env)

    return _run_command(
        cmd,
        cwd=cwd,
        env=merged_env,
        check=False,
        capture_output=True,
        discard_stdin=True,
        timeout=timeout,
    )
