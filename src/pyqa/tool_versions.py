# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Caching and retrieval of tool version information."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

_VERSION_FILE = "tool-versions.json"


def load_versions(cache_dir: Path) -> dict[str, str]:
    """Load cached tool versions from *cache_dir*."""

    path = cache_dir / _VERSION_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {
        str(k): str(v)
        for k, v in data.items()
        if isinstance(k, str) and isinstance(v, str)
    }


def save_versions(cache_dir: Path, versions: Mapping[str, str]) -> None:
    """Persist tool version information into *cache_dir*."""

    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / _VERSION_FILE
    path.write_text(json.dumps(dict(versions), indent=2), encoding="utf-8")
