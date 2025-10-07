# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime preparation and file discovery helpers for orchestrating tools."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from ..config import Config
from ..core.environment import inject_node_defaults, prepend_venv_to_path
from ..core.logging import info
from ..discovery.base import SupportsDiscovery

_RUNTIME_LOG_TEMPLATE: Final[str] = "Discovered %s file(s) to lint"


def prepare_runtime(root: Path | None) -> Path:
    """Resolve the execution root and prime the environment.

    Args:
        root: Optional project root supplied by the caller. ``None`` falls back
            to :func:`Path.cwd`.

    Returns:
        Path: Fully resolved root directory that should anchor execution.
    """

    resolved = root or Path.cwd()
    prepend_venv_to_path(resolved)
    inject_node_defaults()
    return resolved


def discover_files(discovery: SupportsDiscovery, cfg: Config, root: Path) -> list[Path]:
    """Run discovery and filter results to user-provided limits.

    Args:
        discovery: Strategy responsible for collecting candidate files.
        cfg: Full configuration containing discovery directives.
        root: Filesystem root used to resolve relative paths.

    Returns:
        list[Path]: Sorted list of files that should be processed.
    """

    matched_files = discovery.run(cfg.file_discovery, root)
    limits = [entry if entry.is_absolute() else (root / entry) for entry in cfg.file_discovery.limit_to]
    limits = [limit.resolve() for limit in limits]
    if limits:
        matched_files = [path for path in matched_files if is_within_limits(path, limits)]
    info(
        _RUNTIME_LOG_TEMPLATE % len(matched_files),
        use_emoji=cfg.output.emoji,
    )
    return matched_files


def is_within_limits(candidate: Path, limits: Sequence[Path]) -> bool:
    """Return whether ``candidate`` resides under any of the ``limits``.

    Args:
        candidate: Path to evaluate relative to the limit list.
        limits: Absolute paths that bound discovery results.

    Returns:
        bool: ``True`` when ``candidate`` is located beneath at least one limit
        directory, ``False`` otherwise.
    """

    if not limits:
        return True
    return any(_within_limit(candidate, limit) for limit in limits)


def filter_files_for_tool(extensions: Sequence[str], files: Sequence[Path]) -> list[Path]:
    """Filter ``files`` to those matching the tool's configured extensions.

    Args:
        extensions: File names or suffixes that the tool should process.
        files: Candidate files discovered for the run.

    Returns:
        list[Path]: Sorted, deduplicated list of files relevant to the tool.
    """

    if not extensions:
        normalised = {path if path.is_absolute() else path.resolve() for path in files}
        return sorted(normalised, key=str)

    patterns = {ext.lower() for ext in extensions}
    filtered: set[Path] = set()
    for path in files:
        resolved = path if path.is_absolute() else path.resolve()
        name = resolved.name.lower()
        if name in patterns:
            filtered.add(resolved)
            continue
        suffix = resolved.suffix.lower()
        if suffix and suffix in patterns:
            filtered.add(resolved)
            continue
    return sorted(filtered, key=str)


def _within_limit(candidate: Path, limit: Path) -> bool:
    """Return ``True`` when ``candidate`` resides within ``limit``.

    Args:
        candidate: Path under evaluation.
        limit: Limit path provided by configuration.

    Returns:
        bool: ``True`` when ``candidate`` lies inside ``limit``.
    """

    return candidate.is_relative_to(limit)


__all__ = ["discover_files", "filter_files_for_tool", "is_within_limits", "prepare_runtime"]
