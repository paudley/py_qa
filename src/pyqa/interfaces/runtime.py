# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Interfaces describing runtime service registration and resolution."""

from __future__ import annotations

from abc import abstractmethod
from typing import Protocol, runtime_checkable


@runtime_checkable
class ServiceProtocol(Protocol):
    """Represent a service registered with the runtime container."""

    @abstractmethod
    def __repr__(self) -> str:
        """Return a developer-focused representation.

        Returns:
            str: Representation describing the service instance.
        """

        raise NotImplementedError

    @abstractmethod
    def __str__(self) -> str:
        """Return a human-readable representation.

        Returns:
            str: Human-facing description of the service instance.
        """

        raise NotImplementedError


@runtime_checkable
class ServiceProvider(Protocol):
    """Expose zero-argument call semantics for lazily resolved services."""

    @abstractmethod
    def __call__(self) -> ServiceProtocol:
        """Return the resolved service instance.

        Returns:
            ServiceProtocol: Service retrieved from the container.
        """

        raise NotImplementedError

    @abstractmethod
    def __repr__(self) -> str:
        """Return a developer-friendly representation of the provider.

        Returns:
            str: Representation describing the provider.
        """

        raise NotImplementedError


@runtime_checkable
class ServiceFactory(Protocol):
    """Construct service instances using dependency injection context."""

    @abstractmethod
    def __call__(self, container: ServiceRegistryProtocol) -> ServiceProtocol:
        """Return a service produced using ``container``.

        Args:
            container: Service registry providing access to other bindings.

        Returns:
            ServiceProtocol: Newly constructed service instance.
        """

        raise NotImplementedError

    @abstractmethod
    def __repr__(self) -> str:
        """Return a representation describing the factory instance.

        Returns:
            str: Human-readable diagnostics for the factory.
        """

        raise NotImplementedError


@runtime_checkable
class ServiceRegistryProtocol(Protocol):
    """Describe the behaviour required from service registries."""

    @abstractmethod
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
            key: Unique service identifier.
            factory: Factory callable responsible for creating the service.
            singleton: When ``True`` cache the instance after first resolution.
            replace: When ``True`` replace an existing registration for ``key``.
        """
        raise NotImplementedError("ServiceRegistryProtocol.register must be implemented")

    @abstractmethod
    def resolve(self, key: str) -> ServiceProtocol:
        """Return the service registered under ``key``.

        Args:
            key: Unique service identifier.

        Returns:
            ServiceProtocol: Service bound to ``key``.
        """
        raise NotImplementedError("ServiceRegistryProtocol.resolve must be implemented")

    @abstractmethod
    def provide(self, key: str) -> ServiceProvider:
        """Return a lazily resolving provider for ``key``.

        Args:
            key: Unique service identifier.

        Returns:
            ServiceProvider: Zero-argument provider that resolves the service.
        """
        raise NotImplementedError("ServiceRegistryProtocol.provide must be implemented")

    @abstractmethod
    def __contains__(self, key: str) -> bool:
        """Return whether ``key`` has a registered service.

        Args:
            key: Unique service identifier.

        Returns:
            bool: ``True`` when a factory is registered for ``key``.
        """
        raise NotImplementedError("ServiceRegistryProtocol.__contains__ must be implemented")

    @abstractmethod
    def __len__(self) -> int:
        """Return the number of registered services.

        Returns:
            int: Count of registered service factories.
        """
        raise NotImplementedError("ServiceRegistryProtocol.__len__ must be implemented")


__all__ = [
    "ServiceFactory",
    "ServiceProtocol",
    "ServiceProvider",
    "ServiceRegistryProtocol",
]
