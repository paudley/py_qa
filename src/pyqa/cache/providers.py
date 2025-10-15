# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Concrete cache provider implementations."""

from __future__ import annotations

import json
import time
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Generic, TypeVar, cast

from pyqa.core.serialization import SerializableValue, serialize_outcome

from ..interfaces.cache import CacheProvider

ValueT = TypeVar("ValueT")


class InMemoryCacheProvider(CacheProvider[ValueT], Generic[ValueT]):
    """Use this provider to deliver an in-memory cache backed by a dictionary."""

    def __init__(self) -> None:
        """Use this constructor to initialise an empty, thread-safe dictionary."""

        self._store: dict[str, tuple[float | None, ValueT]] = {}
        self._lock = RLock()

    def get(self, key: str) -> ValueT | None:
        """Use this provider to return the cached value for ``key`` when it has not expired.

        Args:
            key: Cache key whose stored value should be retrieved.

        Returns:
            ValueT | None: Cached value when present and unexpired; otherwise ``None``.
        """

        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at is not None and expires_at < now:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: ValueT, *, ttl_seconds: float | None = None) -> None:
        """Use this provider to store ``value`` for ``key`` with an optional TTL.

        Args:
            key: Cache key that should reference ``value``.
            value: Value to store under ``key``.
            ttl_seconds: Optional time-to-live in seconds after which the value expires.
        """

        expires_at = (time.monotonic() + ttl_seconds) if ttl_seconds is not None else None
        with self._lock:
            self._store[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        """Use this provider to remove the cached value stored for ``key``.

        Args:
            key: Cache key whose stored value should be discarded.
        """

        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Remove all cached values maintained by the provider."""

        with self._lock:
            self._store.clear()


class DirectoryCacheProvider(CacheProvider[SerializableValue]):
    """Use this provider to persist cached values on disk as JSON payloads."""

    def __init__(self, directory: Path) -> None:
        """Use this constructor to ensure ``directory`` exists.

        Args:
            directory: Filesystem directory used to persist cache entries.
        """

        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> SerializableValue | None:
        """Use this provider to return the cached value for ``key`` when a JSON payload exists.

        Args:
            key: Cache key whose value should be retrieved.

        Returns:
            SerializableValue | None: Cached JSON payload when present, otherwise ``None``.
        """

        path = self._path_for(key)
        if not path.is_file():
            return None
        try:
            raw_payload = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            payload: SerializableValue = cast(SerializableValue, json.loads(raw_payload))
        except json.JSONDecodeError:
            return None
        return payload

    def set(
        self,
        key: str,
        value: SerializableValue,
        *,
        ttl_seconds: float | None = None,
    ) -> None:
        """Use this provider to persist ``value`` for ``key`` ignoring TTL semantics.

        Args:
            key: Cache key whose payload should be persisted.
            value: Serializable payload to store on disk.
            ttl_seconds: Ignored TTL argument retained for parity with the interface.
        """

        _ = ttl_seconds
        path = self._path_for(key)
        try:
            path.write_text(json.dumps(value, indent=2, default=serialize_outcome), encoding="utf-8")
        except OSError:
            pass

    def delete(self, key: str) -> None:
        """Use this provider to remove the cached JSON entry for ``key`` when it exists.

        Args:
            key: Cache key whose persisted payload should be deleted.
        """

        path = self._path_for(key)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def clear(self) -> None:
        """Remove all cached JSON files managed by the provider."""

        for child in self._directory.glob("*.json"):
            try:
                child.unlink(missing_ok=True)
            except OSError:
                continue

    def _path_for(self, key: str) -> Path:
        """Use this helper to return the filesystem path derived from ``key``.

        Args:
            key: Cache key whose hashed path should be calculated.

        Returns:
            Path: Filesystem path pointing at the cache entry.
        """

        digest = sha256(key.encode("utf-8"), usedforsecurity=False).hexdigest()
        return self._directory / f"{digest}.json"


__all__ = ["DirectoryCacheProvider", "InMemoryCacheProvider"]
