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
from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass
from functools import partial, update_wrapper
from threading import Lock
from types import MethodType
from typing import Final, Generic, ParamSpec, TypeVar, cast

ArgT = TypeVar("ArgT")
KwargT = TypeVar("KwargT")
InstanceT = TypeVar("InstanceT")
HashableCandidate = TypeVar("HashableCandidate", bound=Hashable)

P = ParamSpec("P")
R = TypeVar("R")

CacheKey = Hashable


@dataclass(frozen=True, slots=True)
class CacheInfo:
    """Use this container to describe cache state metadata.

    Attributes:
        current_size: Number of cached entries currently stored.
        hits: Number of cache hits that have occurred.
        maxsize: Configured maximum cache capacity, ``None`` when unbounded.
    """

    current_size: int
    hits: int
    maxsize: int | None


def _build_cache_key(args: tuple[Hashable, ...], kwargs: Mapping[str, Hashable]) -> CacheKey:
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


def _ensure_hashable(value: HashableCandidate, *, label: str) -> HashableCandidate:
    """Return ``value`` ensuring it is hashable for cache key construction.

    Args:
        value: Arbitrary argument value supplied to the cached callable.
        label: Human-readable label used when raising descriptive errors.

    Returns:
        Hashable: The original value when it supports hashing.

    Raises:
        TypeError: If ``value`` is not hashable.
    """

    if isinstance(value, Hashable):
        return value
    raise TypeError(f"{label} must be hashable to participate in caching")


def _hashable_args(args: tuple[ArgT, ...]) -> tuple[Hashable, ...]:
    """Convert positional arguments into a hashable tuple for cache keys.

    Args:
        args: Positional arguments provided to the cached callable.

    Returns:
        tuple[Hashable, ...]: Tuple of hashable positional argument values.
    """

    return tuple(_ensure_hashable(arg, label=f"positional argument {index}") for index, arg in enumerate(args))


def _hashable_kwargs(kwargs: Mapping[str, KwargT]) -> dict[str, Hashable]:
    """Convert keyword arguments into hashable values for cache keys.

    Args:
        kwargs: Keyword arguments provided to the cached callable.

    Returns:
        dict[str, Hashable]: Mapping of keyword names to hashable values.
    """

    return {key: _ensure_hashable(value, label=f"keyword argument '{key}'") for key, value in kwargs.items()}


class _MemoizedCallable(Generic[P, R]):
    """Implement an optional-size LRU cache for callables."""

    def __init__(self, func: Callable[P, R], maxsize: int | None) -> None:
        """Initialise the memoized callable wrapper.

        Args:
            func: Callable whose results should be memoized.
            maxsize: Maximum number of cache entries allowed, ``None`` for unbounded caches.
        """

        self._func = func
        self._maxsize = maxsize
        self._store: OrderedDict[CacheKey, R] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        update_wrapper(self, func)

    # suppression_valid: lint=internal-signatures because decorators must keep functools APIs while exposing __call__.
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Invoke the wrapped callable applying memoization semantics.

        Args:
            *args: Positional arguments forwarded to the wrapped callable.
            **kwargs: Keyword arguments forwarded to the wrapped callable.

        Returns:
            R: Result produced by the wrapped callable.
        """

        hashable_args = _hashable_args(args)
        hashable_kwargs = _hashable_kwargs(kwargs)
        cache_key = _build_cache_key(hashable_args, hashable_kwargs)
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

    def __get__(self, instance: InstanceT | None, owner: type[InstanceT] | None = None) -> Callable[P, R]:
        """Return a descriptor-aware callable bound to ``instance``.

        Args:
            instance: Instance owning the decorated callable.
            owner: Owning class of the descriptor (unused).

        Returns:
            Callable[..., R]: Callable that preserves the memoization behaviour.
        """

        if instance is None:
            return self
        return cast(Callable[P, R], MethodType(self, instance))

    def cache_clear(self) -> None:
        """Reset cached entries and hit tracking."""

        with self._lock:
            self._store.clear()
            self._hits = 0

    def cache_info(self) -> tuple[int, int, int | None]:
        """Return cache metadata mirroring ``functools.lru_cache`` semantics.

        Returns:
            tuple[int, int, int | None]: Tuple of ``(current_size, currsize, maxsize)``.
        """

        metadata = self.cache_metadata()
        return metadata.current_size, metadata.current_size, metadata.maxsize

    def cache_metadata(self) -> CacheInfo:
        """Return cache metadata in a ``CacheInfo`` payload including hits.

        Returns:
            CacheInfo: Cache metadata including current cache size, hits, and
            configured max size.
        """

        with self._lock:
            return CacheInfo(current_size=len(self._store), hits=self._hits, maxsize=self._maxsize)


class _TTLCacheCallable(Generic[P, R]):
    """Implement a time-to-live cache policy for callables."""

    def __init__(self, func: Callable[P, R], ttl_seconds: float) -> None:
        """Initialise the TTL cache wrapper.

        Args:
            func: Callable whose results should be cached.
            ttl_seconds: Time-to-live window in seconds for cached entries.
        """

        self._func = func
        self._ttl_seconds = ttl_seconds
        self._store: dict[CacheKey, tuple[float, R]] = {}
        self._lock = Lock()
        update_wrapper(self, func)

    # suppression_valid: lint=internal-signatures because decorators must expose descriptors for compatibility.
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Invoke the wrapped callable applying TTL caching semantics.

        Args:
            *args: Positional arguments forwarded to the wrapped callable.
            **kwargs: Keyword arguments forwarded to the wrapped callable.

        Returns:
            R: Result produced by the wrapped callable.
        """

        hashable_args = _hashable_args(args)
        hashable_kwargs = _hashable_kwargs(kwargs)
        cache_key = _build_cache_key(hashable_args, hashable_kwargs)
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

    def __get__(self, instance: InstanceT | None, owner: type[InstanceT] | None = None) -> Callable[P, R]:
        """Return a descriptor-aware callable bound to ``instance``.

        Args:
            instance: Instance owning the decorated callable.
            owner: Owning class of the descriptor (unused).

        Returns:
            Callable[..., R]: Callable preserving TTL cache semantics.
        """

        if instance is None:
            return self
        return cast(Callable[P, R], MethodType(self, instance))

    def cache_clear(self) -> None:
        """Reset cached TTL values."""

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
