# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Execution helpers for invoking external commands in a controlled manner."""

from __future__ import annotations

import os
import subprocess  # nosec B404 - required for orchestrating trusted tool commands
from pathlib import Path
from shutil import which as _which
from typing import Mapping, Sequence


def find_executable(cmd: str) -> str | None:
    """Locate an executable on ``PATH`` (virtualenv aware)."""

    return _which(cmd)


def run_command(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command returning a completed process with text outputs."""

    merged_env: dict[str, str] | None = None
    if env:
        merged_env = os.environ.copy()
        merged_env.update(env)

    def _ensure_text(data: str | bytes | None) -> str:
        if isinstance(data, bytes):
            return data.decode(errors="ignore")
        return data or ""

    try:
        return subprocess.run(  # nosec B603 - commands are constructed internally
            list(cmd),
            cwd=str(cwd) if cwd else None,
            env=merged_env,
            text=True,
            capture_output=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        stdout = _ensure_text(exc.stdout)
        stderr_base = _ensure_text(exc.stderr)
        timeout_msg = (
            f"Command timed out after {timeout:.1f}s"
            if timeout is not None
            else "Command timed out"
        )
        stderr = f"{stderr_base}\n{timeout_msg}" if stderr_base else timeout_msg
        return subprocess.CompletedProcess(
            args=list(exc.cmd) if isinstance(exc.cmd, (list, tuple)) else list(cmd),
            returncode=124,
            stdout=stdout,
            stderr=stderr,
        )
