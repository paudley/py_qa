# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Caching and retrieval of tool version information."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

_VERSION_FILE = "tool-versions.json"


def load_versions(cache_dir: Path) -> dict[str, str]:
    """Use this helper to read cached tool versions from ``cache_dir``.

    Args:
        cache_dir: Directory location that may contain the version manifest.

    Returns:
        dict[str, str]: Mapping of tool name to recorded version string.
    """
    path = cache_dir / _VERSION_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def save_versions(cache_dir: Path, versions: Mapping[str, str]) -> None:
    """Use this helper to write tool version information into ``cache_dir``.

    Args:
        cache_dir: Directory where the version manifest should be stored.
        versions: Mapping of tool names to their resolved versions.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / _VERSION_FILE
    path.write_text(json.dumps(dict(versions), indent=2), encoding="utf-8")
