"""Configuration loading and mutation interfaces."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from collections.abc import Mapping, MutableMapping


@runtime_checkable
class ConfigSource(Protocol):
    """Provide configuration data loaded from disk or other mediums."""

    def load(self) -> Mapping[str, object]:
        """Return configuration values as a mapping."""
        ...


@runtime_checkable
class ConfigResolver(Protocol):
    """Resolve layered configuration values into a final mapping."""

    def resolve(self, *sources: Mapping[str, object]) -> Mapping[str, object]:
        """Merge ``sources`` according to resolver semantics."""
        ...


@runtime_checkable
class ConfigMutator(Protocol):
    """Apply overrides to configuration structures."""

    def apply(self, data: MutableMapping[str, object]) -> None:
        """Mutate ``data`` in place."""
        ...
