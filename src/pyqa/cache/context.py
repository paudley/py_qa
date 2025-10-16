# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Helpers for managing execution cache metadata and lifecycle."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ..config import Config
from ..interfaces.cache import CacheContextFactory as CacheContextFactoryProtocol
from ..interfaces.cache import CacheTokenBuilder as CacheTokenBuilderProtocol
from ..interfaces.cache import CacheVersionStore as CacheVersionStoreProtocol
from ..interfaces.cache import (
    ResultCacheFactory,
    ResultCacheProtocol,
)
from .result_store import CachedEntry, CacheRequest, ResultCache
from .tool_versions import load_versions as _load_versions
from .tool_versions import save_versions as _save_versions

_HASH_ENCODING: Final[str] = "utf-8"


@dataclass(slots=True)
class CacheContext:
    """Represent cache configuration for a single orchestrator run."""

    cache: ResultCacheProtocol | None
    token: str | None
    cache_dir: Path
    versions: dict[str, str]
    version_store: CacheVersionStoreProtocol | None = None
    versions_dirty: bool = False

    def load_cached_outcome(
        self,
        *,
        tool_name: str,
        action_name: str,
        cmd: Sequence[str],
        files: Sequence[Path],
    ) -> CachedEntry | None:
        """Return a cached entry for the provided invocation when available.

        Args:
            tool_name: Name of the tool whose command should be resolved.
            action_name: Action identifier for cache segmentation.
            cmd: Concrete command invocation used to execute the tool.
            files: Files that influence the command output.

        Returns:
            CachedEntry | None: Cached response when valid, otherwise ``None``.
        """

        if self.cache is None or self.token is None:
            return None
        request = CacheRequest(
            tool=tool_name,
            action=action_name,
            command=tuple(cmd),
            files=tuple(Path(path) for path in files),
            token=self.token,
        )
        return self.cache.load(request)

    def persist_versions(self) -> None:
        """Use this helper to persist tool versions when the context is marked dirty."""

        if not self.versions_dirty or self.version_store is None:
            return
        self.version_store.save(self.cache_dir, self.versions)
        self.versions_dirty = False


class DefaultCacheTokenBuilder(CacheTokenBuilderProtocol):
    """Generate cache tokens from lint configuration."""

    @property
    def builder_name(self) -> str:
        """Return the identifier of the token builder implementation.

        Returns:
            str: Identifier describing the default token builder.
        """

        return "default-cache-token"

    def build_token(self, config: Config) -> str:
        """Build the cache token representing ``config``.

        Args:
            config: Execution configuration influencing cache scope.

        Returns:
            str: Cache token derived from the supplied configuration.
        """

        exec_cfg = config.execution
        components = [
            str(exec_cfg.strict),
            str(exec_cfg.fix_only),
            str(exec_cfg.check_only),
            str(exec_cfg.force_all),
            str(exec_cfg.respect_config),
            str(exec_cfg.line_length),
            ",".join(sorted(config.severity_rules)),
        ]
        if config.tool_settings:
            serialized = json.dumps(config.tool_settings, sort_keys=True)
            digest = hashlib.sha1(serialized.encode(_HASH_ENCODING), usedforsecurity=False).hexdigest()
            components.append(digest)
        return "|".join(components)

    def __call__(self, config: Config) -> str:
        """Return the cache token to support callable usage.

        Args:
            config: Execution configuration influencing cache scope.

        Returns:
            str: Cache token produced by :meth:`build_token`.
        """

        return self.build_token(config)


class FileSystemCacheVersionStore(CacheVersionStoreProtocol):
    """Manage cache-related tool version metadata on disk."""

    def load(self, directory: Path) -> dict[str, str]:
        """Use this store to load tool version metadata stored under ``directory``.

        Args:
            directory: Directory containing cache metadata.

        Returns:
            dict[str, str]: Mapping of tool names to their recorded versions.
        """

        return dict(_load_versions(directory))

    def save(self, directory: Path, versions: Mapping[str, str]) -> None:
        """Use this store to save tool version metadata within ``directory``.

        Args:
            directory: Target directory for persisted metadata.
            versions: Mapping of tool names to version strings.
        """

        _save_versions(directory, dict(versions))


@dataclass(slots=True)
class ResultCacheClassFactory(ResultCacheFactory):
    """Wrap a cache class so it satisfies the factory protocol."""

    implementation: type[ResultCache]

    @property
    def factory_name(self) -> str:
        """Return the identifier of the wrapped cache class."""

        return self.implementation.__name__

    def __call__(self, directory: Path) -> ResultCacheProtocol:
        """Instantiate the wrapped cache class for ``directory``."""

        return self.implementation(directory)


@dataclass(slots=True)
class DefaultCacheContextFactory(CacheContextFactoryProtocol):
    """Create cache contexts using injectable collaborators."""

    result_cache_factory: ResultCacheFactory
    token_builder: CacheTokenBuilderProtocol
    version_store: CacheVersionStoreProtocol

    @property
    def factory_name(self) -> str:
        """Return the identifier of the cache context factory."""

        return "default-cache-context"

    def build(self, config: Config, root: Path) -> CacheContext:
        """Construct a cache context bound to ``config`` and ``root``.

        Args:
            config: Execution configuration describing cache behaviour.
            root: Project root resolved for the current run.

        Returns:
            CacheContext: Cache context initialised for the run.
        """

        raw_dir = config.execution.cache_dir
        cache_dir = raw_dir if raw_dir.is_absolute() else root / raw_dir
        if not config.execution.cache_enabled:
            return CacheContext(cache=None, token=None, cache_dir=cache_dir, versions={}, version_store=None)

        cache: ResultCacheProtocol = self.result_cache_factory(cache_dir)
        token: str = self.token_builder.build_token(config)
        versions: dict[str, str] = self.version_store.load(cache_dir)
        return CacheContext(
            cache=cache,
            token=token,
            cache_dir=cache_dir,
            versions=versions,
            version_store=self.version_store,
        )


_DEFAULT_TOKEN_BUILDER = DefaultCacheTokenBuilder()
_DEFAULT_VERSION_STORE = FileSystemCacheVersionStore()
_DEFAULT_CONTEXT_FACTORY = DefaultCacheContextFactory(
    result_cache_factory=ResultCacheClassFactory(ResultCache),
    token_builder=_DEFAULT_TOKEN_BUILDER,
    version_store=_DEFAULT_VERSION_STORE,
)


def build_cache_context(cfg: Config, root: Path) -> CacheContext:
    """Build cache helpers for the current configuration.

    Args:
        cfg: Execution configuration describing cache behaviour.
        root: Project root resolved for the current run.

    Returns:
        CacheContext: Cache context configured for the run.
    """

    return _DEFAULT_CONTEXT_FACTORY.build(cfg, root)


def default_cache_context_factory() -> DefaultCacheContextFactory:
    """Return the default cache context factory instance.

    Returns:
        DefaultCacheContextFactory: Shared factory instance.
    """

    return _DEFAULT_CONTEXT_FACTORY


def update_tool_version(context: CacheContext, tool_name: str, version: str | None) -> None:
    """Use this helper to update cached tool version metadata for the active context.

    Args:
        context: Cache context whose version metadata should be updated.
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

    return context.load_cached_outcome(
        tool_name=tool_name,
        action_name=action_name,
        cmd=cmd,
        files=files,
    )


def build_cache_token(cfg: Config) -> str:
    """Generate the cache token representing the effective execution options.

    Args:
        cfg: Execution configuration describing cache behaviour.

    Returns:
        str: Cache token derived from the configuration.
    """

    return _DEFAULT_TOKEN_BUILDER.build_token(cfg)


def load_versions(cache_dir: Path) -> dict[str, str]:
    """Use this helper to return tool version metadata stored on disk.

    Args:
        cache_dir: Directory where tool version metadata is persisted.

    Returns:
        dict[str, str]: Mapping of tool names to recorded versions.
    """

    return _DEFAULT_VERSION_STORE.load(cache_dir)


def save_versions(cache_dir: Path, versions: Mapping[str, str]) -> None:
    """Use this helper to save tool version metadata to disk.

    Args:
        cache_dir: Directory where metadata should be written.
        versions: Mapping of tool names to version strings.
    """

    _DEFAULT_VERSION_STORE.save(cache_dir, versions)


__all__ = [
    "CacheContext",
    "DefaultCacheContextFactory",
    "DefaultCacheTokenBuilder",
    "default_cache_context_factory",
    "FileSystemCacheVersionStore",
    "build_cache_context",
    "build_cache_token",
    "load_cached_outcome",
    "load_versions",
    "save_versions",
    "update_tool_version",
]
