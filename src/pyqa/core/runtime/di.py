"""Minimal dependency injection container used across pyqa."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Callable

from ...console import console_manager


class ServiceResolutionError(KeyError):
    """Raised when a requested service has not been registered."""


@dataclass(frozen=True)
class _ServiceRecord:
    factory: Callable[[ServiceContainer], Any]
    singleton: bool


class ServiceContainer:
    """Lightweight registry for service factories."""

    def __init__(self) -> None:
        self._factories: dict[str, _ServiceRecord] = {}
        self._singletons: dict[str, Any] = {}

    def register(
        self,
        key: str,
        factory: Callable[[ServiceContainer], Any],
        *,
        singleton: bool = True,
        replace: bool = False,
    ) -> None:
        """Register ``factory`` under ``key``.

        Args:
            key: Identifier for the service.
            factory: Callable that accepts the container and returns the service.
            singleton: When ``True`` cache the value; otherwise call the factory
                on every ``resolve``.
            replace: When ``False`` raise ``ValueError`` if ``key`` is already
                registered.
        """

        if not replace and key in self._factories:
            raise ValueError(f"service '{key}' already registered")
        self._factories[key] = _ServiceRecord(factory=factory, singleton=singleton)
        if replace and key in self._singletons:
            self._singletons.pop(key, None)

    def resolve(self, key: str) -> Any:
        """Return the service registered under ``key``."""

        record = self._factories.get(key)
        if record is None:
            raise ServiceResolutionError(key)
        if record.singleton:
            if key not in self._singletons:
                self._singletons[key] = record.factory(self)
            return self._singletons[key]
        return record.factory(self)

    def provide(self, key: str) -> Callable[[], Any]:
        """Return a zero-argument provider that resolves ``key`` lazily."""

        def _provider() -> Any:
            return self.resolve(key)

        return _provider


def register_default_services(container: ServiceContainer) -> None:
    """Populate ``container`` with built-in service factories."""

    container.register(
        "console_factory",
        lambda _: console_manager.get,
    )

    container.register(
        "logger_factory",
        lambda _: __import__("logging").getLogger,
    )

    container.register(
        "serializer",
        lambda _: _JsonSerializer(),
    )


class _JsonSerializer:
    """Simple JSON serializer used as the default service implementation."""

    def dump(self, value: Any) -> str:
        import json

        return json.dumps(value, default=str)

    def load(self, payload: str) -> Any:
        import json

        return json.loads(payload)
