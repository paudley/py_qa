# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Configuration loading and mutation interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pyqa.config.types import ConfigFragment, MutableConfigFragment

if TYPE_CHECKING:
    from pyqa.config.models import Config


@runtime_checkable
class ConfigSource(Protocol):
    """Provide configuration data loaded from disk or other mediums."""

    name: str
    """Identifier describing the configuration source."""

    def load(self) -> ConfigFragment:
        """Return configuration values as a mapping.

        Returns:
            Mapping containing configuration keys and values.
        """
        raise NotImplementedError

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
    def strategy_name(self) -> str:
        """Return the resolver strategy identifier.

        Returns:
            String identifying the resolution strategy.
        """
        raise NotImplementedError("ConfigResolver.strategy_name must be implemented")

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
    def description(self) -> str:
        """Return a human-readable description of the mutator.

        Returns:
            String describing the mutation strategy.
        """
        raise NotImplementedError("ConfigMutator.description must be implemented")

    def apply(self, data: MutableConfigFragment) -> None:
        """Mutate ``data`` in place.

        Args:
            data: Mutable mapping that should be updated by the mutator.
        """
        raise NotImplementedError


@runtime_checkable
class ConfigLoader(Protocol):
    """Load configuration values from registered sources."""

    @property
    def target_name(self) -> str:
        """Return the name of the configuration target being loaded.

        Returns:
            String identifying the configuration payload being produced.
        """
        raise NotImplementedError("ConfigLoader.target_name must be implemented")

    def load(self, *, strict: bool = False) -> Config:
        """Return the resolved configuration object.

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
