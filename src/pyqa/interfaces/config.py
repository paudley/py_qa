# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Configuration loading and mutation interfaces."""

# pylint: disable=too-few-public-methods

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class ConfigSource(Protocol):
    """Provide configuration data loaded from disk or other mediums."""

    name: str

    def load(self) -> Mapping[str, object]:
        """Return configuration values as a mapping."""
        raise NotImplementedError

    def describe(self) -> str:
        """Return a human-readable description of the source."""
        raise NotImplementedError


@runtime_checkable
class ConfigResolver(Protocol):
    """Resolve layered configuration values into a final mapping."""

    def resolve(self, *sources: Mapping[str, object]) -> Mapping[str, object]:
        """Merge ``sources`` according to resolver semantics."""
        raise NotImplementedError


@runtime_checkable
class ConfigMutator(Protocol):
    """Apply overrides to configuration structures."""

    def apply(self, data: MutableMapping[str, object]) -> None:
        """Mutate ``data`` in place."""
        raise NotImplementedError
