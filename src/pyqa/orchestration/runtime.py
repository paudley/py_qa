# SPDX-License-Identifier: MIT
"""Runtime helpers for orchestrator file discovery and filtering."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from pyqa.config import Config
from pyqa.discovery.base import SupportsDiscovery, is_within_limits, resolve_limit_paths


def prepare_runtime(root: Path | None) -> Path:
    """Return the resolved project root used for orchestration.

    Args:
        root: Optional override supplied by the caller.

    Returns:
        Path: Resolved filesystem root.
    """

    return root.resolve() if root is not None else Path.cwd()


def discover_files(discovery: SupportsDiscovery, cfg: Config, root: Path) -> list[Path]:
    """Return files discovered by ``discovery`` using the config settings.

    Args:
        discovery: Discovery strategy bundle used to gather candidate files.
        cfg: Normalised configuration describing discovery options.
        root: Repository root used for discovery resolution.

    Returns:
        list[Path]: Sorted list of unique, resolved file paths.
    """

    files = discovery.run(cfg.file_discovery, root)
    limits = resolve_limit_paths(cfg.file_discovery.limit_to, root)
    return sorted({path.resolve() for path in files if is_within_limits(path.resolve(), limits)})


def filter_files_for_tool(extensions: Iterable[str], files: Sequence[Path]) -> list[Path]:
    """Return files matching the provided ``extensions``.

    Args:
        extensions: File suffixes a tool operates on.
        files: Candidate files discovered for the run.

    Returns:
        list[Path]: Ordered subset of files acceptable to the tool.
    """

    normalized = {ext.lower() for ext in extensions if ext}
    if not normalized:
        return list(files)
    return [path for path in files if path.suffix.lower() in normalized]


__all__ = ["discover_files", "filter_files_for_tool", "prepare_runtime"]
