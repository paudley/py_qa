# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Concrete cache provider implementations."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Dict, Generic, Iterable, Tuple, TypeVar

from pyqa.core.serialization import JsonValue, SerializableValue, serialize_outcome

from ..interfaces.cache import CacheProvider

ValueT = TypeVar("ValueT")


class InMemoryCacheProvider(CacheProvider[ValueT], Generic[ValueT]):
    """Provide an in-memory cache backed by a dictionary."""

    def __init__(self) -> None:
        self._store: Dict[str, Tuple[float | None, ValueT]] = {}
        self._lock = RLock()

    def get(self, key: str) -> ValueT | None:
        """Return the cached value for ``key`` when it has not expired."""

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
        """Store ``value`` for ``key`` with an optional TTL."""

        expires_at = (time.monotonic() + ttl_seconds) if ttl_seconds is not None else None
        with self._lock:
            self._store[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        """Remove the cached value stored for ``key``."""

        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Remove all cached values maintained by the provider."""

        with self._lock:
            self._store.clear()


class DirectoryCacheProvider(CacheProvider[SerializableValue]):
    """Persist cached values on disk as JSON payloads."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> SerializableValue | None:
        """Return the cached value for ``key`` when a JSON payload exists."""

        path = self._path_for(key)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def set(
        self,
        key: str,
        value: SerializableValue,
        *,
        ttl_seconds: float | None = None,
    ) -> None:
        """Persist ``value`` for ``key`` ignoring TTL semantics."""

        _ = ttl_seconds
        path = self._path_for(key)
        try:
            path.write_text(json.dumps(value, indent=2, default=serialize_outcome), encoding="utf-8")
        except OSError:
            return

    def delete(self, key: str) -> None:
        """Remove the cached JSON entry for ``key`` when it exists."""

        path = self._path_for(key)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return

    def clear(self) -> None:
        """Remove all cached JSON files managed by the provider."""

        for child in self._directory.glob("*.json"):
            try:
                child.unlink(missing_ok=True)
            except OSError:
                continue

    def _path_for(self, key: str) -> Path:
        digest = sha256(key.encode("utf-8"), usedforsecurity=False).hexdigest()
        return self._directory / f"{digest}.json"


__all__ = ["DirectoryCacheProvider", "InMemoryCacheProvider"]
