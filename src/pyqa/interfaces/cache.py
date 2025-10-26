# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Cache provider contracts shared across pyqa."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar, runtime_checkable

ValueT = TypeVar("ValueT")

if TYPE_CHECKING:
    from pyqa.cache.context import CacheContext
    from pyqa.cache.result_store import CachedEntry, CacheRequest
    from pyqa.config.models import Config
    from pyqa.core.metrics import FileMetrics
    from pyqa.core.models import ToolOutcome


class CacheProvider(Protocol, Generic[ValueT]):
    """Define the contract implemented by cache backends.

    Implementations should treat cache operations as pure functions whose side
    effects remain scoped to the provider. Thread safety is implementation
    specific, so callers must not assume atomicity unless the provider
    documents it. Values persisted by long-lived providers must be
    JSON-serialisable so directory or remote caches can round-trip data.
    """

    @abstractmethod
    def get(self, key: str) -> ValueT | None:
        """Fetch the cached value associated with ``key`` when present.

        Args:
            key: Unique identifier representing the cached entry.

        Returns:
            ValueT | None: Cached value when present and valid, otherwise ``None``.
        """
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: ValueT, *, ttl_seconds: float | None = None) -> None:
        """Store ``value`` under ``key`` with an optional TTL expressed in seconds.

        Args:
            key: Unique identifier representing the cached entry.
            value: Value to store under ``key``.
            ttl_seconds: Optional time-to-live in seconds; ``None`` disables expiry.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove any cached value associated with ``key``.

        Args:
            key: Unique identifier representing the cached entry to remove.
        """
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Remove all cached values managed by the provider."""
        raise NotImplementedError


@runtime_checkable
class ResultCacheProtocol(Protocol):
    """Define the contract satisfied by result cache backends."""

    @abstractmethod
    def load(self, request: CacheRequest) -> CachedEntry | None:
        """Return the cached entry recorded for ``request`` when available.

        Args:
            request: Cache request describing the desired entry.

        Returns:
            CachedEntry | None: Cached entry when available; otherwise ``None``.
        """
        raise NotImplementedError

    @abstractmethod
    def store(
        self,
        request: CacheRequest,
        *,
        outcome: ToolOutcome,
        file_metrics: Mapping[str, FileMetrics] | None = None,
    ) -> None:
        """Persist ``outcome`` for ``request`` alongside optional metrics.

        Args:
            request: Cache request describing the stored entry.
            outcome: Tool outcome captured for the cache request.
            file_metrics: Optional metrics collected for files processed by the tool.
        """
        raise NotImplementedError


class ResultCacheFactory(Protocol):
    """Construct result cache instances bound to a directory."""

    @property
    @abstractmethod
    def factory_name(self) -> str:
        """Return the human-readable name of the cache factory.

        Returns:
            str: Identifier describing the concrete cache factory implementation.
        """
        raise NotImplementedError

    @abstractmethod
    def __call__(self, directory: Path) -> ResultCacheProtocol:
        """Create a cache instance rooted at ``directory``.

        Args:
            directory: Filesystem directory that should own the cache contents.

        Returns:
            ResultCacheProtocol: Cache instance scoped to ``directory``.
        """
        raise NotImplementedError


class CacheVersionStore(Protocol):
    """Provide persistence for cache-aware tool version metadata."""

    @abstractmethod
    def load(self, directory: Path) -> dict[str, str]:
        """Return tool version metadata stored under ``directory``.

        Args:
            directory: Directory associated with the cache metadata.

        Returns:
            dict[str, str]: Mapping of tool identifiers to recorded versions.
        """
        raise NotImplementedError

    @abstractmethod
    def save(self, directory: Path, versions: Mapping[str, str]) -> None:
        """Persist ``versions`` within ``directory``.

        Args:
            directory: Directory associated with the cache metadata.
            versions: Tool version mapping to persist.
        """
        raise NotImplementedError


class CacheTokenBuilder(Protocol):
    """Generate cache tokens from lint configuration."""

    @property
    @abstractmethod
    def builder_name(self) -> str:
        """Return the identifier of the token builder implementation.

        Returns:
            str: Identifier describing the concrete builder.
        """
        raise NotImplementedError

    @abstractmethod
    def build_token(self, config: Config) -> str:
        """Return the cache token representing ``config``.

        Args:
            config: Lint configuration to derive the cache token from.

        Returns:
            str: Cache token representing ``config``.
        """
        raise NotImplementedError


class CacheContextFactory(Protocol):
    """Create cache contexts for lint executions."""

    @property
    @abstractmethod
    def factory_name(self) -> str:
        """Return the identifier of the cache context factory.

        Returns:
            str: Identifier describing the concrete context factory implementation.
        """
        raise NotImplementedError

    @abstractmethod
    def build(self, config: Config, root: Path) -> CacheContext:
        """Return the cache context bound to ``config`` and ``root``.

        Args:
            config: Active lint configuration.
            root: Repository root used for cache derivation.

        Returns:
            CacheContext: Cache context configured for the execution.
        """
        raise NotImplementedError


__all__ = [
    "CacheContextFactory",
    "CacheProvider",
    "CacheTokenBuilder",
    "CacheVersionStore",
    "ResultCacheFactory",
    "ResultCacheProtocol",
]
