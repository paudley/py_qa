# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

from __future__ import annotations

import time

from pyqa.cache import ttl_cache


def test_ttl_cache_caches_until_expiry(monkeypatch):
    calls = {"count": 0}

    @ttl_cache(ttl_seconds=0.1)
    def compute(value: int) -> int:
        calls["count"] += 1
        return value * 2

    assert compute(2) == 4
    assert compute(2) == 4
    assert calls["count"] == 1

    time.sleep(0.11)
    assert compute(2) == 4
    assert calls["count"] == 2


def test_ttl_cache_clear():
    calls = {"count": 0}

    @ttl_cache(ttl_seconds=60)
    def compute(value: int) -> int:
        calls["count"] += 1
        return value * 2

    compute(3)
    compute(3)
    assert calls["count"] == 1
    compute.cache_clear()
    compute(3)
    assert calls["count"] == 2
