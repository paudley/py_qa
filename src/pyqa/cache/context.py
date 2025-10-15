# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Helpers for managing execution cache metadata and lifecycle."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ..config import Config
from .result_store import CachedEntry, CacheRequest, ResultCache
from .tool_versions import load_versions as _load_versions
from .tool_versions import save_versions as _save_versions

_HASH_ENCODING: Final[str] = "utf-8"


@dataclass(slots=True)
class CacheContext:
    """Represent cache configuration for a single orchestrator run."""

    cache: ResultCache | None
    token: str | None
    cache_dir: Path
    versions: dict[str, str]
    versions_dirty: bool = False


def build_cache_context(cfg: Config, root: Path) -> CacheContext:
    """Initialize cache helpers for the current configuration.

    Args:
        cfg: Top-level execution configuration.
        root: Resolved project root for this run.

    Returns:
        CacheContext: Contextual cache information used throughout the run.
    """

    cache_dir = cfg.execution.cache_dir if cfg.execution.cache_dir.is_absolute() else root / cfg.execution.cache_dir
    if not cfg.execution.cache_enabled:
        return CacheContext(cache=None, token=None, cache_dir=cache_dir, versions={})
    cache = ResultCache(cache_dir)
    token = build_cache_token(cfg)
    versions = load_versions(cache_dir)
    return CacheContext(cache=cache, token=token, cache_dir=cache_dir, versions=versions)


def update_tool_version(context: CacheContext, tool_name: str, version: str | None) -> None:
    """Use this helper to update tool version metadata for the active cache context.

    Args:
        context: Cache context tracking version metadata.
        tool_name: Logical tool identifier.
        version: Resolved tool version string.
    """

    if not version:
        return
    if context.versions.get(tool_name) == version:
        return
    context.versions[tool_name] = version
    context.versions_dirty = True


def load_cached_outcome(
    context: CacheContext,
    *,
    tool_name: str,
    action_name: str,
    cmd: Sequence[str],
    files: Sequence[Path],
) -> CachedEntry | None:
    """Return a cached entry for the provided invocation when available.

    Args:
        context: Cache context bound to the current run.
        tool_name: Name of the tool whose command should be resolved.
        action_name: Action identifier for cache segmentation.
        cmd: Concrete command invocation used to execute the tool.
        files: Files that influence the command output.

    Returns:
        CachedEntry | None: Cached response when valid, otherwise ``None``.
    """

    if context.cache is None or context.token is None:
        return None
    request = CacheRequest(
        tool=tool_name,
        action=action_name,
        command=tuple(cmd),
        files=tuple(Path(path) for path in files),
        token=context.token,
    )
    return context.cache.load(request)


def build_cache_token(cfg: Config) -> str:
    """Generate the cache token representing the effective execution options.

    Args:
        cfg: Configuration whose relevant properties influence caching.

    Returns:
        str: Stable cache token combining execution flags and tool settings.
    """

    exec_cfg = cfg.execution
    components = [
        str(exec_cfg.strict),
        str(exec_cfg.fix_only),
        str(exec_cfg.check_only),
        str(exec_cfg.force_all),
        str(exec_cfg.respect_config),
        str(exec_cfg.line_length),
        ",".join(sorted(cfg.severity_rules)),
    ]
    if cfg.tool_settings:
        serialized = json.dumps(cfg.tool_settings, sort_keys=True)
        digest = hashlib.sha1(serialized.encode(_HASH_ENCODING), usedforsecurity=False).hexdigest()
        components.append(digest)
    return "|".join(components)


def load_versions(cache_dir: Path) -> dict[str, str]:
    """Use this helper to return tool version metadata previously persisted to disk.

    Args:
        cache_dir: Directory where tool version metadata is stored.

    Returns:
        dict[str, str]: Mapping of tool name to version string.
    """

    return _load_versions(cache_dir)


def save_versions(cache_dir: Path, versions: dict[str, str]) -> None:
    """Write tool version metadata to disk.

    Args:
        cache_dir: Destination directory for the metadata file.
        versions: Mapping of tool names to their resolved versions.
    """

    _save_versions(cache_dir, versions)


__all__ = [
    "CacheContext",
    "build_cache_context",
    "build_cache_token",
    "load_cached_outcome",
    "load_versions",
    "save_versions",
    "update_tool_version",
]
