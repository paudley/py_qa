# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI-facing protocol definitions used across the project."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeAlias, runtime_checkable

CliParameterValue: TypeAlias = str | int | float | bool | None
"""Scalar types accepted by CLI invocation payloads."""

CommandResult: TypeAlias = int | None
CommandCallable: TypeAlias = Callable[..., CommandResult]
CommandDecorator: TypeAlias = Callable[[CommandCallable], CommandCallable]


@dataclass(frozen=True, slots=True)
class CommandRegistrationOptions:
    """Optional parameters controlling Typer command registration."""

    add_help_option: bool = True
    help_text: str | None = None
    hidden: bool = False


@dataclass(frozen=True, slots=True)
class CliInvocation:
    """Describe the arguments passed to a CLI callback.

    Attributes:
        args: Positional arguments supplied to the command function.
        kwargs: Keyword arguments supplied to the command function.
    """

    args: tuple[CliParameterValue, ...]
    kwargs: Mapping[str, CliParameterValue]


@runtime_checkable
class CliCommand(Protocol):
    """Protocol implemented by typed command objects."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the human-friendly command name.

        Returns:
            str: Human-friendly command identifier.
        """

    @abstractmethod
    def execute(self, invocation: CliInvocation) -> CommandResult:
        """Execute the command using the provided invocation payload.

        Args:
            invocation: Structured CLI invocation payload.

        Returns:
            CommandResult: Exit code returned by the command or ``None`` when unspecified.
        """


@runtime_checkable
class CliCommandFactory(Protocol):
    """Protocol implemented by factories that construct CLI commands."""

    @property
    @abstractmethod
    def command_name(self) -> str:
        """Return the identifier assigned to the constructed command.

        Returns:
            str: Command name associated with the factory output.
        """

    @abstractmethod
    def create(self, argv: Sequence[str] | None = None) -> CliCommand:
        """Create a command instance optionally initialised with ``argv``.

        Args:
            argv: Optional sequence of CLI arguments provided to the command.

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
    ) -> CommandDecorator:
        """Register a command on the sub-application.

        Args:
            name: Optional override for the command name.
            help_text: Optional help text rendered in CLI usage output.
            add_help_option: Whether an automatic ``--help`` option should be registered.
            hidden: ``True`` when the command should be hidden from help output.

        Returns:
            CommandDecorator: Decorator used to register the command callable.
        """

    @abstractmethod
    def callback(
        self,
        *,
        invoke_without_command: bool = False,
    ) -> CommandDecorator:
        """Register a callback on the sub-application.

        Args:
            invoke_without_command: When ``True`` invoke the callback even if no command is selected.

        Returns:
            CommandDecorator: Decorator used to register the callback callable.
        """


@runtime_checkable
class TyperLike(TyperSubApplication, Protocol):
    """Structural protocol mirroring the Typer command surface."""

    @abstractmethod
    def add_typer(self, sub_command: TyperSubApplication, *, name: str | None = None) -> None:
        """Attach a nested CLI application as a sub-command.

        Args:
            sub_command: Typer application to add as a nested command.
            name: Optional override for the sub-command name.
        """
