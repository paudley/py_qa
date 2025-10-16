# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Configuration loading and mutation interfaces."""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pyqa.config.types import ConfigFragment, MutableConfigFragment

if TYPE_CHECKING:
    from pyqa.config.models import Config


@runtime_checkable
class ConfigSource(Protocol):
    """Provide configuration data loaded from disk or other mediums."""

    name: str
    """Identifier describing the configuration source."""

    @abstractmethod
    def load(self) -> ConfigFragment:
        """Provide configuration values as a mapping.

        Returns:
            Mapping containing configuration keys and values.
        """
        raise NotImplementedError

    @abstractmethod
    def describe(self) -> str:
        """Return a human-readable description of the source.

        Returns:
            Short textual summary of the configuration source.
        """
        raise NotImplementedError


@runtime_checkable
class ConfigResolver(Protocol):
    """Resolve layered configuration values into a final mapping."""

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Return the resolver strategy identifier.

        Returns:
            String identifying the resolution strategy.
        """
        raise NotImplementedError

    @abstractmethod
    def resolve(self, *sources: ConfigFragment) -> ConfigFragment:
        """Merge ``sources`` according to resolver semantics.

        Args:
            *sources: Configuration mappings to merge in priority order.

        Returns:
            Mapping containing the merged configuration payload.
        """
        raise NotImplementedError


@runtime_checkable
class ConfigMutator(Protocol):
    """Apply overrides to configuration structures."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a human-readable description of the mutator.

        Returns:
            String describing the mutation strategy.
        """
        raise NotImplementedError

    @abstractmethod
    def apply(self, data: MutableConfigFragment) -> None:
        """Apply mutations to ``data`` in place.

        Args:
            data: Mutable mapping that should be updated by the mutator.
        """
        raise NotImplementedError


@runtime_checkable
class ConfigLoader(Protocol):
    """Define an interface that loads configuration values from registered sources."""

    @property
    @abstractmethod
    def target_name(self) -> str:
        """Return the name of the configuration target being loaded.

        Returns:
            String identifying the configuration payload being produced.
        """
        raise NotImplementedError

    @abstractmethod
    def load(self, *, strict: bool = False) -> Config:
        """Load the resolved configuration object.

        Args:
            strict: When ``True`` enforce strict validation semantics.

        Returns:
            Configuration object loaded by the concrete implementation.
        """

        raise NotImplementedError


__all__ = [
    "ConfigLoader",
    "ConfigMutator",
    "ConfigResolver",
    "ConfigSource",
]
