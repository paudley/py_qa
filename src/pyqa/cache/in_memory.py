# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""In-memory caching decorators shared across the project."""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from threading import Lock
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def ttl_cache(ttl_seconds: float) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Return a decorator implementing a simple TTL cache.

    Args:
        ttl_seconds: Number of seconds a cached value remains valid.

    Returns:
        Callable[..., R]: Decorated callable with ``cache_clear`` attribute.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        lock = Lock()
        store: dict[Any, tuple[float, R]] = {}

        def _make_key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
            if not kwargs:
                return args
            return args, tuple(sorted(kwargs.items()))

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = _make_key(args, kwargs)
            now = time.monotonic()
            with lock:
                entry = store.get(key)
                if entry is not None:
                    expires_at, value = entry
                    if expires_at >= now:
                        return value
            result = func(*args, **kwargs)
            with lock:
                store[key] = (now + ttl_seconds, result)
            return result

        def cache_clear() -> None:
            with lock:
                store.clear()

        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        return wrapper

    return decorator


__all__ = ["ttl_cache"]
