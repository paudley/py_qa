# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared helpers for CLI commands."""

from __future__ import annotations

import json
import subprocess  # nosec B404 - subprocess used for controlled CLI invocations
from pathlib import Path
from typing import List

PYQA_ROOT = Path(__file__).resolve().parent.parent


def installed_packages() -> set[str]:
    """Return the set of installed packages within the project environment."""

    try:
        completed = subprocess.run(  # nosec - arguments are fixed and trusted
            ["uv", "pip", "list", "--format=json"],
            check=True,
            capture_output=True,
            text=True,
            cwd=PYQA_ROOT,
        )
    except (OSError, subprocess.CalledProcessError):
        return set()
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return set()
    return {str(item.get("name", "")).lower() for item in data if isinstance(item, dict) and item.get("name")}


def run_uv(args: List[str], *, check: bool = True) -> None:
    """Invoke ``uv`` with *args* relative to the project root."""

    subprocess.run(  # nosec - caller controls arguments without shell
        args, check=check, cwd=PYQA_ROOT
    )
