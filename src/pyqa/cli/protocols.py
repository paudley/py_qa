# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI protocols describing the Typer surface consumed throughout pyqa."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import typer

from pyqa.interfaces.cli import CliCommand, CliCommandFactory, CliInvocation, TyperLike, TyperSubApplication

CliParameterValue = str | int | float | bool | None
CommandResult = int | None
CommandCallable = Callable[..., CommandResult]
CommandDecorator = Callable[[CommandCallable], CommandCallable]


@dataclass(frozen=True, slots=True)
class TyperAdapter(TyperLike):
    """Adapter that exposes a :class:`typer.Typer` instance through ``TyperLike``."""

    app: typer.Typer

    def command(
        self,
        name: str | None = None,
        *,
        help_text: str | None = None,
        add_help_option: bool = True,
        hidden: bool = False,
    ) -> CommandDecorator:
        """Return a decorator that registers a CLI command.

        Args:
            name: Optional explicit command name used during registration.
            help_text: Optional help text shown in CLI usage output.
            add_help_option: Whether the ``--help`` option should be registered.
            hidden: ``True`` when the command should be hidden from help output.

        Returns:
            CommandDecorator: Decorator returned by the underlying Typer app.
        """

        decorator = self.app.command(
            name=name,
            help=help_text,
            add_help_option=add_help_option,
            hidden=hidden,
        )
        return cast(CommandDecorator, decorator)

    def callback(
        self,
        *,
        invoke_without_command: bool = False,
    ) -> CommandDecorator:
        """Return a decorator registering an application-level callback.

        Args:
            invoke_without_command: Whether the callback executes without a sub-command.

        Returns:
            CommandDecorator: Decorator returned by the underlying Typer app.
        """

        decorator = self.app.callback(invoke_without_command=invoke_without_command)
        return cast(CommandDecorator, decorator)

    def add_typer(self, sub_command: TyperSubApplication | typer.Typer, *, name: str | None = None) -> None:
        """Attach a nested Typer application to the current application.

        Args:
            sub_command: Typer-compatible application registered as a sub-command.
            name: Optional explicit sub-command name under which ``sub_command`` is registered.

        Raises:
            TypeError: Raised when ``sub_command`` is not Typer-compatible.
        """

        if isinstance(sub_command, TyperAdapter):
            self.app.add_typer(sub_command.app, name=name)
            return
        if isinstance(sub_command, typer.Typer):
            self.app.add_typer(sub_command, name=name)
            return
        raise TypeError("add_typer expects a Typer-compatible application")


def wrap_typer(app: typer.Typer) -> TyperAdapter:
    """Return a :class:`TyperAdapter` that proxies ``app`` through ``TyperLike``.

    Args:
        app: Concrete Typer application to wrap.

    Returns:
        TyperAdapter: Adapter exposing the minimal Typer surface consumed by pyqa.
    """

    return TyperAdapter(app)


__all__ = [
    "CliCommand",
    "CliCommandFactory",
    "CliInvocation",
    "CliParameterValue",
    "CommandCallable",
    "CommandDecorator",
    "CommandResult",
    "TyperLike",
    "TyperSubApplication",
    "TyperAdapter",
    "wrap_typer",
]
