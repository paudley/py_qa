# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""In-memory caching decorators shared across the project.

The helpers defined here intentionally avoid nested closures so that they play
nicely with the ``closures`` lint while still exposing an ergonomic API that
mirrors ``functools`` caches.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from functools import partial, update_wrapper
from threading import Lock
from types import MethodType
from typing import Any, Final, Generic, ParamSpec, TypeVar, cast

P = ParamSpec("P")
R = TypeVar("R")

CacheKey = Hashable


@dataclass(frozen=True, slots=True)
class CacheInfo:
    """Metadata describing the state of a cache.

    Attributes:
        current_size: Number of cached entries currently stored.
        hits: Number of cache hits that have occurred.
        maxsize: Configured maximum cache capacity, ``None`` when unbounded.
    """

    current_size: int
    hits: int
    maxsize: int | None


def _build_cache_key(args: tuple[Hashable, ...], kwargs: dict[str, Hashable]) -> CacheKey:
    """Construct a stable hashable cache key.

    Args:
        args: Positional arguments supplied to the wrapped callable.
        kwargs: Keyword arguments supplied to the wrapped callable.

    Returns:
        CacheKey: Tuple-based representation suitable for dict access.
    """

    if not kwargs:
        return args
    return args + (tuple(sorted(kwargs.items())),)


class _MemoizedCallable(Generic[P, R]):
    """Callable that implements an optional-size LRU cache."""

    def __init__(self, func: Callable[P, R], maxsize: int | None) -> None:
        self._func = func
        self._maxsize = maxsize
        self._store: OrderedDict[CacheKey, R] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        update_wrapper(self, func)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Invoke the wrapped callable applying memoization semantics.

        Args:
            *args: Positional arguments forwarded to the wrapped callable.
            **kwargs: Keyword arguments forwarded to the wrapped callable.

        Returns:
            R: Result produced by the wrapped callable.
        """

        cache_key = _build_cache_key(args, kwargs)
        with self._lock:
            cached = self._store.get(cache_key)
            if cached is not None:
                self._store.move_to_end(cache_key)
                self._hits += 1
                return cached
        result = self._func(*args, **kwargs)
        with self._lock:
            self._store[cache_key] = result
            if self._maxsize is not None and len(self._store) > self._maxsize:
                self._store.popitem(last=False)
        return result

    def __get__(self, instance: object, owner: type[Any] | None = None) -> Callable[..., R]:
        """Return a descriptor-aware callable bound to ``instance``.

        Args:
            instance: Instance owning the decorated callable.
            owner: Owning class of the descriptor (unused).

        Returns:
            Callable[..., R]: Callable that preserves the memoization behaviour.
        """

        if instance is None:
            return self
        return MethodType(self, instance)

    def cache_clear(self) -> None:
        """Clear cached entries and reset hit tracking.

        Returns:
            None
        """

        with self._lock:
            self._store.clear()
            self._hits = 0

    def cache_info(self) -> CacheInfo:
        """Return cache metadata in a ``CacheInfo`` payload.

        Returns:
            CacheInfo: Snapshot describing the cache state.
        """

        with self._lock:
            return CacheInfo(current_size=len(self._store), hits=self._hits, maxsize=self._maxsize)


class _TTLCacheCallable(Generic[P, R]):
    """Callable that applies a time-to-live cache policy."""

    def __init__(self, func: Callable[P, R], ttl_seconds: float) -> None:
        self._func = func
        self._ttl_seconds = ttl_seconds
        self._store: dict[CacheKey, tuple[float, R]] = {}
        self._lock = Lock()
        update_wrapper(self, func)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Invoke the wrapped callable applying TTL caching semantics.

        Args:
            *args: Positional arguments forwarded to the wrapped callable.
            **kwargs: Keyword arguments forwarded to the wrapped callable.

        Returns:
            R: Result produced by the wrapped callable.
        """

        cache_key = _build_cache_key(args, kwargs)
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(cache_key)
            if entry is not None:
                expires_at, value = entry
                if expires_at >= now:
                    return value
        result = self._func(*args, **kwargs)
        with self._lock:
            self._store[cache_key] = (now + self._ttl_seconds, result)
        return result

    def __get__(self, instance: object, owner: type[Any] | None = None) -> Callable[..., R]:
        """Return a descriptor-aware callable bound to ``instance``.

        Args:
            instance: Instance owning the decorated callable.
            owner: Owning class of the descriptor (unused).

        Returns:
            Callable[..., R]: Callable preserving TTL cache semantics.
        """

        if instance is None:
            return self
        return MethodType(self, instance)

    def cache_clear(self) -> None:
        """Clear cached TTL values.

        Returns:
            None
        """

        with self._lock:
            self._store.clear()


def memoize(maxsize: int | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Return a decorator implementing an optional-size LRU cache.

    Args:
        maxsize: Maximum number of entries to retain. ``None`` disables the cap.

    Returns:
        Callable[[Callable[P, R]], Callable[P, R]]: Decorator preserving cache helpers.
    """

    decorator = partial(_apply_memoize, maxsize=maxsize)
    return cast(Callable[[Callable[P, R]], Callable[P, R]], decorator)


def ttl_cache(ttl_seconds: float) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Return a decorator implementing a simple TTL cache.

    Args:
        ttl_seconds: Number of seconds a cached value remains valid.

    Returns:
        Callable[[Callable[P, R]], Callable[P, R]]: Decorator preserving TTL helpers.
    """

    decorator = partial(_apply_ttl_cache, ttl_seconds=ttl_seconds)
    return cast(Callable[[Callable[P, R]], Callable[P, R]], decorator)


def _apply_memoize(func: Callable[P, R], *, maxsize: int | None) -> Callable[P, R]:
    """Return a memoized callable wrapping ``func``.

    Args:
        func: Callable receiving memoization.
        maxsize: Maximum cache capacity for the wrapped callable.

    Returns:
        Callable[P, R]: Memoized callable with cache helpers attached.
    """

    memoized = _MemoizedCallable(func, maxsize)
    return cast(Callable[P, R], memoized)


def _apply_ttl_cache(func: Callable[P, R], *, ttl_seconds: float) -> Callable[P, R]:
    """Return a TTL-cached callable wrapping ``func``.

    Args:
        func: Callable receiving TTL caching semantics.
        ttl_seconds: Cache lifetime in seconds.

    Returns:
        Callable[P, R]: TTL cached callable with helper APIs.
    """

    ttl_wrapped = _TTLCacheCallable(func, ttl_seconds)
    return cast(Callable[P, R], ttl_wrapped)


__all__: Final = ["memoize", "ttl_cache", "CacheInfo"]
