"""Core service interfaces shared across the project."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ConsoleFactory(Protocol):
    """Factory returning console instances honouring colour/emoji settings."""

    def __call__(self, *, color: bool, emoji: bool) -> Any:
        """Return a console-like object supporting ``print``."""

        ...


@runtime_checkable
class LoggerFactory(Protocol):
    """Factory returning structured loggers."""

    def __call__(self, name: str) -> Any:
        """Return a logger identified by ``name``."""

        ...


@runtime_checkable
class Serializer(Protocol):
    """Serialize/deserialize model instances."""

    def dump(self, value: Any) -> str:
        """Return the serialized representation of ``value``."""

        ...

    def load(self, payload: str) -> Any:
        """Return a model instance deserialized from ``payload``."""

        ...
