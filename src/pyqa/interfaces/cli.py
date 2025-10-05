"""Interfaces describing CLI command orchestration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from collections.abc import Sequence


@runtime_checkable
class CliCommand(Protocol):
    """Represent a Typer-compatible command callable."""

    def __call__(self, *args, **kwargs) -> int | None:
        """Execute the command and optionally return an exit code."""
        ...


@runtime_checkable
class CliCommandFactory(Protocol):
    """Factory used to construct CLI commands with injected dependencies."""

    def create(self, argv: Sequence[str] | None = None) -> CliCommand:
        """Return a CLI command configured for the provided arguments."""
        ...
