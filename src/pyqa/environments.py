# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Environment helpers for locating virtualenvs and preparing subprocess contexts."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path
from typing import Final

WINDOWS_OS_NAME: Final[str] = "nt"

NODE_ENV_DEFAULTS: Final[dict[str, str]] = {
    "CI": "1",
    "npm_config_yes": "true",
    "npm_config_fund": "false",
    "npm_config_audit": "false",
    "npm_config_progress": "false",
    "NPX_SILENT": "1",
}


def find_venv_bin(root: Path | None = None) -> Path | None:
    """Find the virtualenv bin/Scripts directory relative to *root*.

    The search walks up from ``root`` until the filesystem root, looking for
    either ``.venv`` or ``venv`` directories.
    """
    root = (root or Path.cwd()).resolve()
    search_paths = [root, *root.parents]
    for candidate in search_paths:
        for name in (".venv", "venv"):
            venv_dir = candidate / name
            if not venv_dir.is_dir():
                continue
            bin_dir = venv_dir / ("Scripts" if os.name == WINDOWS_OS_NAME else "bin")
            if bin_dir.is_dir():
                return bin_dir
    return None


def prepend_venv_to_path(
    root: Path | None = None,
    env: MutableMapping[str, str] | None = None,
) -> Path | None:
    """Ensure the virtualenv ``bin`` directory is first on PATH.

    Returns the resolved bin path if one was added, otherwise ``None``.
    """
    env = env if env is not None else os.environ
    venv_bin = find_venv_bin(root)
    if not venv_bin:
        return None
    path = env.get("PATH", "")
    env["PATH"] = str(venv_bin) + (os.pathsep + path if path else "")
    return venv_bin


def inject_node_defaults(env: MutableMapping[str, str] | None = None) -> None:
    """Apply default environment variables for Node-based tooling."""
    env = env if env is not None else os.environ
    for key, value in NODE_ENV_DEFAULTS.items():
        env.setdefault(key, value)
