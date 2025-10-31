# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Shared utilities for CLI commands (logging, errors, registration)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Generic, TypeVar, cast, overload

import typer
from rich.console import Console
from rich.text import Text

from pyqa.cli.protocols import TyperLike
from pyqa.protocols.cli import CommandRegistrationOptions

from ...core.logging import fail as core_fail
from ...core.logging import ok as core_ok
from ...core.logging import warn as core_warn


class CLIError(RuntimeError):
    """Error raised when a CLI command fails and should exit with a status code."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        """Initialise the error with a message and exit code.

        Args:
            message: Human-readable error message shown to the user.
            exit_code: Exit status associated with the failure.
        """

        super().__init__(message)
        self.exit_code = exit_code


@dataclass(slots=True)
class CLILogger:
    """Adapter around project logging helpers respecting CLI emoji settings."""

    console: Console
    use_emoji: bool
    debug_enabled: bool = False
    _key_value_re: re.Pattern[str] = re.compile(r"([\w-]+)=(\".*?\"|\S+)")

    def fail(self, message: str) -> None:
        """Log a failure message honouring emoji preferences.

        Args:
            message: Text describing the failure state.
        """

        core_fail(message, use_emoji=self.use_emoji)

    def warn(self, message: str) -> None:
        """Log a warning message honouring emoji preferences.

        Args:
            message: Text describing the warning condition.
        """

        core_warn(message, use_emoji=self.use_emoji)

    def ok(self, message: str) -> None:
        """Log a success message honouring emoji preferences.

        Args:
            message: Text describing the successful state.
        """

        core_ok(message, use_emoji=self.use_emoji)

    def echo(self, message: str) -> None:
        """Write ``message`` to stdout using Typer's echo helper.

        Args:
            message: Text written to standard output.
        """

        typer.echo(message)

    def debug(self, message: str) -> None:
        """Emit a debug message when debug logging is enabled.

        Args:
            message: Debug payload rendered with simple highlighting.
        """

        if self.debug_enabled:
            text = Text("[debug] ", style="bold cyan")
            cursor = 0
            for match in self._key_value_re.finditer(message):
                start, end = match.span()
                if start > cursor:
                    text.append(message[cursor:start], style="dim")
                key, raw_value = match.group(1), match.group(2)
                text.append(key, style="bold magenta")
                text.append("=", style="dim")
                value_style = "bold green"
                if key in {"command", "cmd"}:
                    value_style = "bold blue"
                text.append(raw_value, style=value_style)
                cursor = end
            if cursor < len(message):
                text.append(message[cursor:], style="dim")
            self.console.print(text)


def build_cli_logger(*, emoji: bool, debug: bool = False, no_color: bool = False) -> CLILogger:
    """Return a ``CLILogger`` configured for the provided emoji preference.

    Args:
        emoji: Whether log output may include emoji glyphs.
        debug: Whether debug logging should be enabled.
        no_color: Whether terminal colour output should be disabled.

    Returns:
        CLILogger: Logger instance bound to a dedicated Rich console.
    """

    console = Console(no_color=no_color, highlight=False)
    return CLILogger(console=console, use_emoji=emoji, debug_enabled=debug)


DependencyT = TypeVar("DependencyT")


@dataclass(slots=True)
class Depends(Generic[DependencyT]):
    """Describe a dependency callable for Typer-compatible injection."""

    dependency: Callable[..., DependencyT]
    use_cache: bool = True


CommandResult = int | None
CommandCallable = Callable[..., CommandResult]
CommandDecoratorCallable = Callable[[CommandCallable], CommandCallable]


@dataclass(slots=True)
class _CommandDecorator:
    """Callable helper registering Typer commands without nested closures."""

    app: TyperLike
    name: str | None
    help_text: str | None

    def __call__(self, func: CommandCallable) -> CommandCallable:
        """Register ``func`` as a Typer command and return the registered callback.

        Args:
            func: Callable executed when the CLI command runs.

        Returns:
            CommandCallable: Callback returned by Typer registration.
        """

        try:
            decorator: CommandDecoratorCallable = self.app.command(
                name=self.name,
                help_text=self.help_text,
            )
        except TypeError:
            typer_app = cast(typer.Typer, self.app)
            command_fn = cast(Callable[..., CommandDecoratorCallable], typer_app.command)
            decorator = command_fn(name=self.name, help=self.help_text)
        return decorator(func)


@dataclass(slots=True)
class _CallbackDecorator:
    """Callable helper registering Typer callbacks with cached metadata."""

    app: TyperLike
    invoke_without_command: bool

    def __call__(self, func: CommandCallable) -> CommandCallable:
        """Register ``func`` as a Typer callback and return the wrapped callable.

        Args:
            func: Callback executed when the Typer application is invoked.

        Returns:
            CommandCallable: Callback returned by Typer registration.
        """

        decorator: CommandDecoratorCallable = self.app.callback(
            invoke_without_command=self.invoke_without_command,
        )
        return decorator(func)


def command_decorator(
    app: TyperLike,
    *,
    name: str | None = None,
    help_text: str | None = None,
) -> CommandDecoratorCallable:
    """Return a decorator that registers a command when applied.

    Args:
        app: Typer-compatible application receiving the command registration.
        name: Optional explicit command name to register.
        help_text: Help text displayed in CLI usage output.

    Returns:
        CommandDecoratorCallable: Decorator that registers *callback* and
        passes it through unchanged.
    """

    helper = _CommandDecorator(
        app=app,
        name=name,
        help_text=help_text,
    )
    return helper


@overload
def register_command(
    app: TyperLike,
    callback: CommandCallable,
    *,
    name: str | None = None,
    help_text: str | None = None,
) -> CommandCallable:
    """Overload enabling immediate registration.

    Args:
        app: Typer-compatible application receiving the command registration.
        callback: Command callable registered immediately.
        name: Optional explicit command name.
        help_text: Optional help text displayed in CLI usage output.

    Returns:
        CommandCallable: Registered command callable returned by Typer.
    """
    ...


@overload
def register_command(
    app: TyperLike,
    callback: None = ...,
    *,
    name: str | None = None,
    help_text: str | None = None,
) -> CommandDecoratorCallable:
    """Overload returning a decorator for deferred registration.

    Args:
        app: Typer-compatible application receiving the command registration.
        name: Optional explicit command name.
        help_text: Optional help text displayed in CLI usage output.

    Returns:
        CommandDecoratorCallable: Decorator used to register the command lazily.
    """
    ...


def register_command(
    app: TyperLike,
    callback: CommandCallable | None = None,
    *,
    name: str | None = None,
    help_text: str | None = None,
) -> CommandDecoratorCallable | CommandCallable:
    """Register a command on ``app`` with consistent metadata handling.

    Args:
        app: Typer-compatible application receiving the command registration.
        callback: Optional callable to register immediately.
        name: Optional explicit command name.
        help_text: Help text shown in CLI usage output.

    Returns:
        CommandDecoratorCallable | CommandCallable: Either the registered callback or
        a decorator for deferred registration.
    """

    decorator = command_decorator(
        app,
        name=name,
        help_text=help_text,
    )
    if callback is not None:
        return decorator(callback)
    return decorator


def callback_decorator(
    app: TyperLike,
    *,
    invoke_without_command: bool = False,
) -> CommandDecoratorCallable:
    """Return a decorator that registers a Typer callback when applied.

    Args:
        app: Typer-compatible application receiving the callback registration.
        invoke_without_command: Whether the callback fires without subcommands.

    Returns:
        CommandDecoratorCallable: Decorator registering a callback when applied.
    """

    helper = _CallbackDecorator(
        app=app,
        invoke_without_command=invoke_without_command,
    )
    return helper


@overload
def register_callback(
    app: TyperLike,
    callback: CommandCallable,
    *,
    invoke_without_command: bool = False,
) -> CommandCallable:
    """Overload supporting immediate callback registration.

    Args:
        app: Typer-compatible application receiving the callback registration.
        callback: Callback registered immediately on the application.
        invoke_without_command: Whether the callback should run without subcommands.

    Returns:
        CommandCallable: Registered callback returned by Typer.
    """
    ...


@overload
def register_callback(
    app: TyperLike,
    callback: None = ...,
    *,
    invoke_without_command: bool = False,
) -> CommandDecoratorCallable:
    """Overload returning a decorator for deferred callback registration.

    Args:
        app: Typer-compatible application receiving the callback registration.
        invoke_without_command: Whether the callback should run without subcommands.

    Returns:
        CommandDecoratorCallable: Decorator used to register the callback lazily.
    """
    ...


def register_callback(
    app: TyperLike,
    callback: CommandCallable | None = None,
    *,
    invoke_without_command: bool = False,
) -> CommandDecoratorCallable | CommandCallable:
    """Register a Typer callback on ``app`` with consistent defaults.

    Args:
        app: Typer-compatible application receiving the callback registration.
        callback: Optional callable to register immediately.
        invoke_without_command: Whether the callback triggers without
            subcommands.

    Returns:
        CommandDecoratorCallable | CommandCallable: Either the registered callback or
        a decorator for deferred registration.
    """

    decorator = callback_decorator(
        app,
        invoke_without_command=invoke_without_command,
    )
    if callback is not None:
        return decorator(callback)
    return decorator


__all__: Final = [
    "CLIError",
    "CLILogger",
    "build_cli_logger",
    "Depends",
    "command_decorator",
    "register_command",
    "callback_decorator",
    "register_callback",
]
