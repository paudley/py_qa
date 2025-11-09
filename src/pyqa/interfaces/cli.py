# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Protocols describing the CLI integration surface."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class CliInvocation(Protocol):
    """Describe the arguments supplied to a CLI callback."""

    @property
    @abstractmethod
    def args(self) -> Sequence[str | int | float | bool | None]:
        """Return positional arguments forwarded to the callback.

        Returns:
            Sequence[str | int | float | bool | None]: Positional CLI argument values.
        """

    @property
    @abstractmethod
    def kwargs(self) -> Mapping[str, str | int | float | bool | None]:
        """Return keyword arguments forwarded to the callback.

        Returns:
            Mapping[str, str | int | float | bool | None]: Keyword CLI argument values.
        """


@runtime_checkable
class CliCommand(Protocol):
    """Protocol implemented by typed CLI command objects."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the human-friendly command name.

        Returns:
            str: Human-readable command identifier.
        """

    @abstractmethod
    def execute(self, invocation: CliInvocation) -> int | None:
        """Execute the command using ``invocation``.

        Args:
            invocation: Structured invocation payload containing CLI arguments.

        Returns:
            int | None: Exit code emitted by the command.
        """


@runtime_checkable
class CliCommandFactory(Protocol):
    """Protocol implemented by factories that construct CLI commands."""

    @property
    @abstractmethod
    def command_name(self) -> str:
        """Return the identifier assigned to constructed commands.

        Returns:
            str: Command name used when registering factory output.
        """

    @abstractmethod
    def create(self, argv: Sequence[str] | None = None) -> CliCommand:
        """Return a command instance optionally initialised with ``argv``.

        Args:
            argv: Optional sequence of CLI arguments supplied to the factory.

        Returns:
            CliCommand: Command instance constructed by the factory.
        """


@runtime_checkable
class TyperSubApplication(Protocol):
    """Protocol describing nested CLI applications accepted by Typer."""

    @abstractmethod
    def command(
        self,
        name: str | None = None,
        *,
        help_text: str | None = None,
        add_help_option: bool = True,
        hidden: bool = False,
    ) -> Callable[[Callable[..., int | None]], Callable[..., int | None]]:
        """Return a decorator that registers a command.

        Args:
            name: Optional explicit command name.
            help_text: Help text displayed in CLI usage output.
            add_help_option: Whether an automatic ``--help`` option should be registered.
            hidden: ``True`` when the command should be hidden from help output.

        Returns:
            Callable[[Callable[..., int | None]], Callable[..., int | None]]: Decorator applied to
            command implementations.
        """

    @abstractmethod
    def callback(
        self,
        *,
        invoke_without_command: bool = False,
    ) -> Callable[[Callable[..., int | None]], Callable[..., int | None]]:
        """Return a decorator that registers an application-level callback.

        Args:
            invoke_without_command: When ``True`` invoke the callback even if no sub-command is selected.

        Returns:
            Callable[[Callable[..., int | None]], Callable[..., int | None]]: Decorator applied to
            callback implementations.
        """


@runtime_checkable
class TyperLike(TyperSubApplication, Protocol):
    """Structural protocol mirroring the Typer command surface."""

    @abstractmethod
    def add_typer(self, sub_command: TyperSubApplication, *, name: str | None = None) -> None:
        """Attach a nested CLI application as a sub-command.

        Args:
            sub_command: Typer-compatible application registered beneath the current app.
            name: Optional explicit sub-command name.
        """


__all__ = [
    "CliCommand",
    "CliCommandFactory",
    "CliInvocation",
    "TyperLike",
    "TyperSubApplication",
]
