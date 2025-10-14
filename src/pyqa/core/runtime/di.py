# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Minimal dependency injection container used across pyqa."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Protocol, cast

from pyqa.core.serialization import JsonValue
from pyqa.runtime.console.manager import get_console_manager

from ...cache import ResultCache, build_cache_context
from ...plugins import (
    load_all_plugins,
    load_catalog_plugins,
    load_cli_plugins,
    load_diagnostics_plugins,
)


class ServiceResolutionError(KeyError):
    """Raised when a requested service has not been registered."""


class Service(Protocol):
    """Marker protocol satisfied by all container service values."""


@dataclass(frozen=True)
class _ServiceRecord:
    factory: Callable[[ServiceContainer], Service]
    singleton: bool


class ServiceContainer:
    """Lightweight registry for service factories."""

    def __init__(self) -> None:
        self._factories: dict[str, _ServiceRecord] = {}
        self._singletons: dict[str, Service] = {}

    def register(
        self,
        key: str,
        factory: Callable[[ServiceContainer], Service],
        *,
        singleton: bool = True,
        replace: bool = False,
    ) -> None:
        """Register ``factory`` under ``key``."""

        if not replace and key in self._factories:
            raise ValueError(f"service '{key}' already registered")
        self._factories[key] = _ServiceRecord(factory=factory, singleton=singleton)
        if replace and key in self._singletons:
            self._singletons.pop(key, None)

    def resolve(self, key: str) -> Service:
        """Return the service registered under ``key``."""

        record = self._factories.get(key)
        if record is None:
            raise ServiceResolutionError(key)
        if record.singleton:
            if key not in self._singletons:
                self._singletons[key] = record.factory(self)
            return self._singletons[key]
        return record.factory(self)

    def provide(self, key: str) -> Callable[[], Service]:
        """Return a zero-argument provider that resolves ``key`` lazily."""

        return partial(self.resolve, key)

    def __contains__(self, key: str) -> bool:
        """Return ``True`` when ``key`` corresponds to a registered service."""

        return key in self._factories

    def __len__(self) -> int:
        """Return the number of services registered with the container."""

        return len(self._factories)


def register_default_services(container: ServiceContainer) -> None:
    """Populate ``container`` with built-in service factories."""

    container.register(
        "console_factory",
        lambda _: get_console_manager().get,
    )

    container.register(
        "logger_factory",
        lambda _: __import__("logging").getLogger,
    )

    container.register(
        "serializer",
        lambda _: _JsonSerializer(),
    )

    container.register(
        "cache_context_builder",
        lambda _: build_cache_context,
        singleton=False,
    )

    container.register(
        "result_cache_factory",
        lambda _: ResultCache,
        singleton=False,
    )

    container.register(
        "catalog_plugins",
        lambda _: load_catalog_plugins,
        singleton=False,
    )
    container.register(
        "cli_plugins",
        lambda _: load_cli_plugins,
        singleton=False,
    )
    container.register(
        "diagnostics_plugins",
        lambda _: load_diagnostics_plugins,
        singleton=False,
    )
    container.register(
        "all_plugins",
        lambda _: load_all_plugins,
        singleton=False,
    )


class _JsonSerializer:
    """Default JSON serializer used by the service container."""

    def dump(self, value: JsonValue) -> str:
        return json.dumps(value, default=str)

    def load(self, payload: str) -> JsonValue:
        return cast(JsonValue, json.loads(payload))
