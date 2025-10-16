# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Unit tests covering cache context factories and collaborators."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pyqa.cache.context import (
    CacheContext,
    DefaultCacheContextFactory,
    DefaultCacheTokenBuilder,
    FileSystemCacheVersionStore,
)
from pyqa.config.models import Config
from pyqa.interfaces.cache import CacheVersionStore, ResultCacheFactory, ResultCacheProtocol


@dataclass
class _RecordingCache(ResultCacheProtocol):
    response: object | None = None
    requests: list[object] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.requests is None:
            self.requests = []

    def load(self, request):  # type: ignore[override]
        self.requests.append(request)
        return self.response

    def store(self, request, *, outcome, file_metrics=None):  # type: ignore[override]
        raise NotImplementedError("store should not be called in tests")


class _RecordingFactory(ResultCacheFactory):
    @property
    def factory_name(self) -> str:
        return "recording"

    def __init__(self, cache: ResultCacheProtocol | None = None) -> None:
        self.cache = cache or _RecordingCache()
        self.calls: list[Path] = []

    def __call__(self, directory: Path) -> ResultCacheProtocol:
        self.calls.append(directory)
        return self.cache


class _RecordingVersionStore(CacheVersionStore):
    def __init__(self, load_result: Mapping[str, str] | None = None) -> None:
        self.load_result = dict(load_result or {})
        self.loaded: list[Path] = []
        self.saved: list[tuple[Path, dict[str, str]]] = []

    def load(self, directory: Path) -> dict[str, str]:
        self.loaded.append(directory)
        return dict(self.load_result)

    def save(self, directory: Path, versions: Mapping[str, str]) -> None:
        self.saved.append((directory, dict(versions)))


def test_cache_context_factory_disabled_skips_dependencies(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.cache_enabled = False

    factory = DefaultCacheContextFactory(
        result_cache_factory=_RecordingFactory(),
        token_builder=DefaultCacheTokenBuilder(),
        version_store=_RecordingVersionStore({"tool": "1.2.3"}),
    )

    context = factory.build(cfg, tmp_path)

    assert context.cache is None
    assert context.token is None
    assert context.version_store is None
    assert context.cache_dir == tmp_path / ".lint-cache"


def test_cache_context_factory_enabled_invokes_dependencies(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.cache_enabled = True
    cfg.execution.cache_dir = Path(".lint-cache")

    cache = _RecordingCache()
    factory = _RecordingFactory(cache)
    version_store = _RecordingVersionStore({"ruff": "0.5.0"})

    token_builder = DefaultCacheTokenBuilder()
    context_factory = DefaultCacheContextFactory(
        result_cache_factory=factory,
        token_builder=token_builder,
        version_store=version_store,
    )

    context = context_factory.build(cfg, tmp_path)

    assert factory.calls == [tmp_path / ".lint-cache"]
    assert version_store.loaded == [tmp_path / ".lint-cache"]
    assert context.cache is cache
    assert context.token == token_builder.build_token(cfg)
    assert context.versions == {"ruff": "0.5.0"}
    assert context.version_store is version_store


def test_cache_context_persist_versions(tmp_path: Path) -> None:
    context = CacheContext(
        cache=None,
        token=None,
        cache_dir=tmp_path,
        versions={"tool": "1.0"},
        version_store=_RecordingVersionStore(),
    )

    context.persist_versions()
    assert not context.version_store.saved  # No write when not dirty

    context.versions_dirty = True
    context.persist_versions()
    assert context.version_store.saved == [(tmp_path, {"tool": "1.0"})]
    assert not context.versions_dirty


def test_cache_context_loads_outcome(tmp_path: Path) -> None:
    cache = _RecordingCache(response="hit")
    context = CacheContext(
        cache=cache,
        token="token",
        cache_dir=tmp_path,
        versions={},
        version_store=None,
    )

    result = context.load_cached_outcome(
        tool_name="tool",
        action_name="action",
        cmd=("cmd", "arg"),
        files=(tmp_path / "file.py",),
    )

    assert result == "hit"
    assert len(cache.requests) == 1
    request = cache.requests[0]
    assert request.tool == "tool"
    assert request.action == "action"
    assert request.command == ("cmd", "arg")
    assert request.token == "token"


def test_cache_context_load_without_token_returns_none(tmp_path: Path) -> None:
    cache = _RecordingCache(response="hit")
    context = CacheContext(
        cache=cache,
        token=None,
        cache_dir=tmp_path,
        versions={},
        version_store=None,
    )

    assert context.load_cached_outcome(
        tool_name="tool",
        action_name="action",
        cmd=("cmd",),
        files=(),
    ) is None
    assert not cache.requests
