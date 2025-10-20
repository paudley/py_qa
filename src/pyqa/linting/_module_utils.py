# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utilities for resolving module metadata used by phase-9 linters."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pyqa.cache.in_memory import memoize

_PACKAGE_SENTINEL: Final[str] = "pyqa"
_INIT_SENTINEL: Final[str] = "__init__"


@memoize(maxsize=1024)
def module_name_from_path(path: Path, root: Path) -> str:
    """Return the fully-qualified module name for ``path`` relative to ``root``.

    Args:
        path: Source file whose module name should be computed.
        root: Workspace root as detected by the CLI (repository root).

    Returns:
        Fully-qualified module path (``pyqa.foo.bar``). When ``path`` does not
        reside beneath ``root`` we fall back to best-effort inference using
        the first occurrence of the ``pyqa`` sentinel in the absolute path.
    """

    path = path.resolve()
    root = root.resolve()
    try:
        relative = path.relative_to(root)
    except ValueError:
        parts = path.parts
        if _PACKAGE_SENTINEL in parts:
            index = parts.index(_PACKAGE_SENTINEL)
            module_parts = parts[index:]
        else:
            module_parts = path.with_suffix("").parts
    else:
        module_parts = relative.with_suffix("").parts
        if _PACKAGE_SENTINEL in module_parts:
            index = module_parts.index(_PACKAGE_SENTINEL)
            module_parts = module_parts[index:]
        else:
            module_parts = (_PACKAGE_SENTINEL, *module_parts)

    if module_parts and module_parts[-1] == _INIT_SENTINEL:
        module_parts = module_parts[:-1]
    if not module_parts:
        return _PACKAGE_SENTINEL
    return ".".join(module_parts)


__all__ = ["module_name_from_path"]
