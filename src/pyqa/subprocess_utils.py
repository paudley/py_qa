# SPDX-License-Identifier: MIT
"""Safe wrappers around ``subprocess`` execution."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Mapping, Sequence


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
) -> subprocess.CompletedProcess[str]:
    """Execute *args* after normalising the executable path."""

    normalized = _normalize_args(args)
    return subprocess.run(
        normalized,
        cwd=str(cwd) if cwd is not None else None,
        env=dict(env) if env is not None else None,
        check=check,
        capture_output=capture_output,
        text=text,
    )


__all__ = ["run_command"]
