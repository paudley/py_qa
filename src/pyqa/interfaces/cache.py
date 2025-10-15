# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Cache provider contracts shared across pyqa."""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar

ValueT = TypeVar("ValueT")


class CacheProvider(Protocol, Generic[ValueT]):
    """Define the contract implemented by cache backends."""

    def get(self, key: str) -> ValueT | None:
        """Return the cached value associated with ``key`` when present."""
        ...

    def set(self, key: str, value: ValueT, *, ttl_seconds: float | None = None) -> None:
        """Store ``value`` under ``key`` with an optional TTL in seconds."""
        ...

    def delete(self, key: str) -> None:
        """Remove any cached value associated with ``key``."""
        ...

    def clear(self) -> None:
        """Remove all cached values managed by the provider."""
        ...


__all__ = ["CacheProvider"]
