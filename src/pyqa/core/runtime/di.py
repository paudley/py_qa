# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Minimal dependency injection container used across pyqa."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import cast

from pyqa.core.serialization import JsonValue, SerializableValue
from pyqa.interfaces.cache import CacheProvider
from pyqa.interfaces.runtime import ServiceFactory, ServiceProtocol, ServiceProvider, ServiceRegistryProtocol
from pyqa.runtime.console.manager import get_console_manager

from ...cache import create_cache_provider, default_cache_provider
from ...cache.context import (
    DefaultCacheTokenBuilder,
    FileSystemCacheVersionStore,
    build_cache_context,
    default_cache_context_factory,
)
from ...cache.result_store import ResultCache
from ...plugins import (
    load_all_plugins,
    load_catalog_plugins,
    load_cli_plugins,
    load_diagnostics_plugins,
)


class ServiceResolutionError(KeyError):
    """Raise when a requested service has not been registered."""


@dataclass(frozen=True)
class _ServiceRecord:
    """Store metadata about a registered service factory."""

    factory: ServiceFactory
    singleton: bool


class ServiceContainer(ServiceRegistryProtocol):
    """Provide a lightweight registry for service factories."""

    def __init__(self) -> None:
        """Initialise an empty service registry."""

        self._factories: dict[str, _ServiceRecord] = {}
        self._singletons: dict[str, ServiceProtocol] = {}

    def register(
        self,
        key: str,
        factory: ServiceFactory,
        *,
        singleton: bool = True,
        replace: bool = False,
    ) -> None:
        """Register ``factory`` under ``key``.

        Args:
            key: Unique service identifier used during lookups.
            factory: Callable responsible for constructing the service instance.
            singleton: When ``True`` the service is cached after the first resolution.
            replace: When ``True`` replace an existing registration for ``key``.

        Raises:
            ValueError: If a service is already registered and ``replace`` is ``False``.
        """

        if not replace and key in self._factories:
            raise ValueError(f"service '{key}' already registered")
        self._factories[key] = _ServiceRecord(factory=factory, singleton=singleton)
        if replace and key in self._singletons:
            self._singletons.pop(key, None)

    def resolve(self, key: str) -> ServiceProtocol:
        """Resolve the service registered under ``key``.

        Args:
            key: Unique service identifier.

        Returns:
            ServiceProtocol: Concrete instance produced by the registered factory.

        Raises:
            ServiceResolutionError: If no factory is registered for ``key``.
        """

        record = self._factories.get(key)
        if record is None:
            raise ServiceResolutionError(key)
        if record.singleton:
            if key not in self._singletons:
                self._singletons[key] = record.factory(self)
            return self._singletons[key]
        return record.factory(self)

    def provide(self, key: str) -> ServiceProvider:
        """Return a zero-argument provider that resolves ``key`` lazily.

        Args:
            key: Unique service identifier.

        Returns:
            ServiceProvider: Provider function that returns the service on demand.
        """

        return partial(self.resolve, key)

    def __contains__(self, key: str) -> bool:
        """Return whether ``key`` corresponds to a registered service.

        Args:
            key: Unique service identifier.

        Returns:
            bool: ``True`` when the key is registered with a factory.
        """

        return key in self._factories

    def __len__(self) -> int:
        """Return the number of services registered with the container.

        Returns:
            int: Count of registered service factories.
        """

        return len(self._factories)

    def __repr__(self) -> str:
        """Return a developer-facing representation summarising registrations.

        Returns:
            str: Description containing known service keys.
        """

        keys = ", ".join(sorted(self._factories))
        return f"ServiceContainer(keys=[{keys}])"


@dataclass(frozen=True, slots=True)
class _StaticServiceFactory(ServiceFactory):
    """Wrap callables so they satisfy the :class:`ServiceFactory` protocol."""

    name: str
    builder: Callable[[ServiceRegistryProtocol], ServiceProtocol]

    def __call__(self, container: ServiceRegistryProtocol) -> ServiceProtocol:
        """Return the service produced by :attr:`builder`.

        Args:
            container: Service registry supplying dependency resolution.

        Returns:
            ServiceProtocol: Service instance produced by the builder.
        """

        return self.builder(container)

    def __repr__(self) -> str:
        """Return a developer-friendly description of the factory.

        Returns:
            str: Identifier capturing the factory name.
        """

        return f"{self.name}_factory"


@dataclass(slots=True)
class _CacheProviderService(CacheProvider[SerializableValue], ServiceProtocol):
    """Adapter that exposes cache providers as :class:`ServiceProtocol` instances."""

    provider: CacheProvider[SerializableValue]

    def __repr__(self) -> str:
        """Return a representation describing the wrapped provider.

        Returns:
            str: Identifier reflecting the provider implementation.
        """

        return f"cache_provider({self.provider!r})"

    def __str__(self) -> str:
        """Return a human-readable description of the wrapped provider.

        Returns:
            str: Description highlighting the provider implementation.
        """

        return str(self.provider)

    def get(self, key: str) -> SerializableValue | None:
        """Return the cached value associated with ``key``.

        Args:
            key: Cache entry identifier.

        Returns:
            SerializableValue | None: Cached value when present.
        """

        return self.provider.get(key)

    def set(self, key: str, value: SerializableValue, *, ttl_seconds: float | None = None) -> None:
        """Store ``value`` under ``key`` with an optional TTL.

        Args:
            key: Cache entry identifier.
            value: Value to cache.
            ttl_seconds: Optional time-to-live expressed in seconds.
        """

        self.provider.set(key, value, ttl_seconds=ttl_seconds)

    def delete(self, key: str) -> None:
        """Remove the cached value associated with ``key``.

        Args:
            key: Cache entry identifier slated for removal.
        """

        self.provider.delete(key)

    def clear(self) -> None:
        """Remove all cached entries maintained by the provider."""

        self.provider.clear()


def _console_factory(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the console provider factory resolved from the console manager.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Callable that retrieves configured console instances.
    """

    return get_console_manager().get


def _logger_factory(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the logger factory from the standard logging module.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Callable producing named logger instances.
    """

    return logging.getLogger


def _serializer_factory(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the JSON serializer used by the runtime container.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Serializer implementation handling JSON payloads.
    """

    return _JsonSerializer()


def _cache_context_builder(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the cache context builder used during orchestration.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Callable constructing cache contexts on demand.
    """

    return build_cache_context


def _cache_context_factory(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the default cache context factory instance.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Callable that creates cache contexts with defaults.
    """

    return default_cache_context_factory()


def _cache_token_builder(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the default cache token builder implementation.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Cache token builder instance.
    """

    return DefaultCacheTokenBuilder()


def _cache_version_store(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the filesystem-backed cache version store implementation.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Cache version store instance.
    """

    return FileSystemCacheVersionStore()


def _cache_provider_factory(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the factory responsible for creating cache providers.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Callable that builds cache providers from settings.
    """

    return create_cache_provider


def _cache_provider(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the default cache provider honouring environment overrides.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Cache provider instance.
    """

    return _CacheProviderService(default_cache_provider())


def _result_cache_factory(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the result cache factory class.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Callable constructing result cache instances.
    """

    return ResultCache


def _catalog_plugins(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the callable that loads catalog plugins.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Callable loading catalog plugins.
    """

    return load_catalog_plugins


def _cli_plugins(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the callable that loads CLI plugins.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Callable loading CLI plugins.
    """

    return load_cli_plugins


def _diagnostics_plugins(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the callable that loads diagnostics plugins.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Callable loading diagnostics plugins.
    """

    return load_diagnostics_plugins


def _all_plugins(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the callable that loads every plugin category.

    Args:
        _: Service registry reference required by the factory protocol.

    Returns:
        ServiceProtocol: Callable loading all plugin namespaces.
    """

    return load_all_plugins


def register_default_services(container: ServiceRegistryProtocol) -> None:
    """Populate ``container`` with built-in service factories.

    Args:
        container: Service registry that receives default registrations.
    """

    def _register_if_missing(
        key: str,
        factory: ServiceFactory,
        *,
        singleton: bool = True,
    ) -> None:
        if key in container:
            return
        container.register(key, factory, singleton=singleton)

    _register_if_missing("console_factory", _StaticServiceFactory("console", _console_factory))

    _register_if_missing("logger_factory", _StaticServiceFactory("logger", _logger_factory))

    _register_if_missing("serializer", _StaticServiceFactory("serializer", _serializer_factory))

    _register_if_missing(
        "cache_context_builder",
        _StaticServiceFactory("cache_context_builder", _cache_context_builder),
        singleton=False,
    )

    _register_if_missing(
        "cache_context_factory",
        _StaticServiceFactory("cache_context_factory", _cache_context_factory),
    )

    _register_if_missing(
        "cache_token_builder",
        _StaticServiceFactory("cache_token_builder", _cache_token_builder),
        singleton=False,
    )

    _register_if_missing(
        "cache_version_store",
        _StaticServiceFactory("cache_version_store", _cache_version_store),
        singleton=False,
    )

    _register_if_missing(
        "cache_provider_factory",
        _StaticServiceFactory("cache_provider_factory", _cache_provider_factory),
        singleton=False,
    )

    _register_if_missing("cache_provider", _StaticServiceFactory("cache_provider", _cache_provider))

    _register_if_missing(
        "result_cache_factory",
        _StaticServiceFactory("result_cache_factory", _result_cache_factory),
        singleton=False,
    )

    _register_if_missing("catalog_plugins", _StaticServiceFactory("catalog_plugins", _catalog_plugins), singleton=False)
    _register_if_missing("cli_plugins", _StaticServiceFactory("cli_plugins", _cli_plugins), singleton=False)
    _register_if_missing(
        "diagnostics_plugins",
        _StaticServiceFactory("diagnostics_plugins", _diagnostics_plugins),
        singleton=False,
    )
    _register_if_missing("all_plugins", _StaticServiceFactory("all_plugins", _all_plugins), singleton=False)


class _JsonSerializer:
    """Provide a JSON serializer used by the service container."""

    @property
    def content_type(self) -> str:
        """Return the MIME type emitted by the serializer.

        Returns:
            str: MIME type describing JSON payloads.
        """

        return "application/json"

    def __repr__(self) -> str:
        """Return a diagnostic representation for debugging.

        Returns:
            str: Representation describing the serializer.
        """

        return "JsonSerializer(content_type='application/json')"

    def __str__(self) -> str:
        """Return a human-readable name for the serializer.

        Returns:
            str: Human-readable descriptor.
        """

        return "JSON serializer"

    def dump(self, value: JsonValue) -> str:
        """Serialise ``value`` to JSON.

        Args:
            value: Serializable payload.

        Returns:
            str: JSON encoded representation of ``value``.
        """

        return json.dumps(value, default=str)

    def load(self, payload: str) -> JsonValue:
        """Deserialize ``payload`` from JSON.

        Args:
            payload: JSON string to decode.

        Returns:
            JsonValue: Decoded payload.
        """

        return cast(JsonValue, json.loads(payload))
