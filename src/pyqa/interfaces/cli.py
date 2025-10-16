# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces describing CLI command orchestration."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeAlias, runtime_checkable

CliParameterValue: TypeAlias = str | int | float | bool | Path | None


@dataclass(frozen=True, slots=True)
class CliInvocation:
    """Bundle positional and keyword arguments for CLI execution."""

    args: tuple[CliParameterValue, ...]
    kwargs: Mapping[str, CliParameterValue]


@runtime_checkable
class CliCommand(Protocol):
    """Execute a Typer-compatible command callable."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the human-friendly name of the command.

        Returns:
            str: User-facing name associated with the command implementation.
        """
        raise NotImplementedError

    @abstractmethod
    def execute(self, invocation: CliInvocation) -> int | None:
        """Execute the command and optionally return an exit code.

        Args:
            invocation: Invocation payload describing positional and keyword arguments.

        Returns:
            int | None: Optional exit code, mirroring Typer semantics.
        """
        raise NotImplementedError


@runtime_checkable
class CliCommandFactory(Protocol):
    """Construct CLI commands with injected dependencies."""

    @property
    @abstractmethod
    def command_name(self) -> str:
        """Return the name of the command constructed by the factory.

        Returns:
            str: Identifier describing the command produced by the factory.
        """
        raise NotImplementedError

    @abstractmethod
    def create(self, argv: Sequence[str] | None = None) -> CliCommand:
        """Create a CLI command configured for the provided arguments.

        Args:
            argv: Optional argument vector used to seed the command.

        Returns:
            CliCommand: Constructed command ready for invocation.
        """
        raise NotImplementedError
