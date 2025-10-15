# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Cache provider contracts shared across pyqa."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar, runtime_checkable

ValueT = TypeVar("ValueT")

if TYPE_CHECKING:
    from pyqa.cache.context import CacheContext
    from pyqa.cache.result_store import CacheRequest, CachedEntry
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

    def get(self, key: str) -> ValueT | None:
        """Return the cached value associated with ``key`` when present.

        Args:
            key: Unique identifier representing the cached entry.

        Returns:
            ValueT | None: Cached value when present and valid, otherwise ``None``.
        """
        ...

    def set(self, key: str, value: ValueT, *, ttl_seconds: float | None = None) -> None:
        """Store ``value`` under ``key`` with an optional TTL in seconds.

        Args:
            key: Unique identifier representing the cached entry.
            value: Value to store under ``key``.
            ttl_seconds: Optional time-to-live in seconds; ``None`` disables expiry.
        """
        ...

    def delete(self, key: str) -> None:
        """Remove any cached value associated with ``key``.

        Args:
            key: Unique identifier representing the cached entry to remove.
        """
        ...

    def clear(self) -> None:
        """Remove all cached values managed by the provider."""


@runtime_checkable
class ResultCacheProtocol(Protocol):
    """Define the contract satisfied by result cache backends."""

    def load(self, request: "CacheRequest") -> "CachedEntry | None":
        """Return the cached entry recorded for ``request`` when available."""

    def store(
        self,
        request: "CacheRequest",
        *,
        outcome: "ToolOutcome",
        file_metrics: Mapping[str, "FileMetrics"] | None = None,
    ) -> None:
        """Persist ``outcome`` for ``request`` with optional ``file_metrics``."""


class ResultCacheFactory(Protocol):
    """Return result cache instances bound to a directory."""

    def __call__(self, directory: Path) -> ResultCacheProtocol:
        """Create a cache instance rooted at ``directory``."""


class CacheVersionStore(Protocol):
    """Provide persistence for cache-aware tool version metadata."""

    def load(self, directory: Path) -> dict[str, str]:
        """Return tool version metadata stored under ``directory``."""

    def save(self, directory: Path, versions: Mapping[str, str]) -> None:
        """Persist ``versions`` within ``directory``."""


class CacheTokenBuilder(Protocol):
    """Generate cache tokens from lint configuration."""

    def build_token(self, config: "Config") -> str:
        """Return the cache token representing ``config``."""


class CacheContextFactory(Protocol):
    """Create cache contexts for lint executions."""

    def build(self, config: "Config", root: Path) -> "CacheContext":
        """Return the cache context bound to ``config`` and ``root``."""


__all__ = [
    "CacheContextFactory",
    "CacheProvider",
    "CacheTokenBuilder",
    "CacheVersionStore",
    "ResultCacheFactory",
    "ResultCacheProtocol",
]
