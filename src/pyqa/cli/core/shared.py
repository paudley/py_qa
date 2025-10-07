# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Shared utilities for CLI commands (logging, errors, registration)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, cast, overload

import typer

from ...core.logging import fail as core_fail
from ...core.logging import ok as core_ok
from ...core.logging import warn as core_warn


class CLIError(RuntimeError):
    """Error raised when a CLI command fails and should exit with a status code."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(slots=True)
class CLILogger:
    """Adapter around project logging helpers respecting CLI emoji settings."""

    use_emoji: bool

    def fail(self, message: str) -> None:
        """Log a failure message honouring emoji preferences."""

        core_fail(message, use_emoji=self.use_emoji)

    def warn(self, message: str) -> None:
        """Log a warning message honouring emoji preferences."""

        core_warn(message, use_emoji=self.use_emoji)

    def ok(self, message: str) -> None:
        """Log a success message honouring emoji preferences."""

        core_ok(message, use_emoji=self.use_emoji)

    def echo(self, message: str) -> None:
        """Write ``message`` to stdout using Typer's echo helper."""

        typer.echo(message)


def build_cli_logger(*, emoji: bool) -> CLILogger:
    """Return a ``CLILogger`` configured for the provided emoji preference."""

    return CLILogger(use_emoji=emoji)


@dataclass(slots=True)
class Depends:
    """Describe a dependency callable for Typer-compatible injection."""

    dependency: Callable[..., Any]
    use_cache: bool = True


CommandParams = ParamSpec("CommandParams")


def command_decorator(
    app: typer.Typer,
    *,
    name: str | None = None,
    help_text: str | None = None,
    **typer_kwargs: Any,
) -> Callable[[Callable[CommandParams, None]], Callable[CommandParams, None]]:
    """Return a decorator that registers a command when applied.

    Args:
        app: Typer application receiving the command registration.
        name: Optional explicit command name to register.
        help_text: Help text displayed in CLI usage output.
        **typer_kwargs: Additional arguments forwarded to ``Typer.command``.

    Returns:
        Callable[[Callback], Callback]: Decorator that registers *callback* and
        passes it through unchanged.
    """

    def decorator(func: Callable[CommandParams, None]) -> Callable[CommandParams, None]:
        registered = app.command(name=name, help=help_text, **typer_kwargs)(cast(Callable[..., Any], func))
        return cast(Callable[CommandParams, None], registered)

    return decorator


@overload
def register_command(
    app: typer.Typer,
    callback: Callable[CommandParams, None],
    *,
    name: str | None = None,
    help_text: str | None = None,
    **typer_kwargs: Any,
) -> Callable[CommandParams, None]: ...


@overload
def register_command(
    app: typer.Typer,
    callback: None = None,
    *,
    name: str | None = None,
    help_text: str | None = None,
    **typer_kwargs: Any,
) -> Callable[[Callable[CommandParams, None]], Callable[CommandParams, None]]: ...


def register_command(
    app: typer.Typer,
    callback: Callable[CommandParams, None] | None = None,
    *,
    name: str | None = None,
    help_text: str | None = None,
    **typer_kwargs: Any,
) -> Callable[[Callable[CommandParams, None]], Callable[CommandParams, None]] | Callable[CommandParams, None]:
    """Register ``callback`` on ``app`` with consistent metadata handling.

    Args:
        app: Typer application receiving the command registration.
        callback: Optional callable to register immediately.
        name: Optional explicit command name.
        help_text: Help text shown in CLI usage output.
        **typer_kwargs: Additional arguments forwarded to ``Typer.command``.

    Returns:
        Callable or callback: Either the registered callback or a decorator for
        deferred registration.
    """

    decorator = command_decorator(app, name=name, help_text=help_text, **typer_kwargs)
    if callback is not None:
        return decorator(callback)
    return decorator


def callback_decorator(
    app: typer.Typer,
    *,
    invoke_without_command: bool = False,
    **typer_kwargs: Any,
) -> Callable[[Callable[CommandParams, None]], Callable[CommandParams, None]]:
    """Return a decorator that registers a Typer callback when applied.

    Args:
        app: Typer application receiving the callback registration.
        invoke_without_command: Whether the callback should run when no
            subcommand is provided.
        **typer_kwargs: Additional arguments forwarded to ``Typer.callback``.

    Returns:
        Callable[[Callback], Callback]: Decorator that registers *callback* and
        returns it unchanged.
    """

    def decorator(func: Callable[CommandParams, None]) -> Callable[CommandParams, None]:
        registered = app.callback(
            invoke_without_command=invoke_without_command,
            **typer_kwargs,
        )(cast(Callable[..., Any], func))
        return cast(Callable[CommandParams, None], registered)

    return decorator


@overload
def register_callback(
    app: typer.Typer,
    callback: Callable[CommandParams, None],
    *,
    invoke_without_command: bool = False,
    **typer_kwargs: Any,
) -> Callable[CommandParams, None]: ...


@overload
def register_callback(
    app: typer.Typer,
    callback: None = None,
    *,
    invoke_without_command: bool = False,
    **typer_kwargs: Any,
) -> Callable[[Callable[CommandParams, None]], Callable[CommandParams, None]]: ...


def register_callback(
    app: typer.Typer,
    callback: Callable[CommandParams, None] | None = None,
    *,
    invoke_without_command: bool = False,
    **typer_kwargs: Any,
) -> Callable[[Callable[CommandParams, None]], Callable[CommandParams, None]] | Callable[CommandParams, None]:
    """Register a Typer callback on ``app`` with consistent defaults.

    Args:
        app: Typer application receiving the callback registration.
        callback: Optional callable to register immediately.
        invoke_without_command: Whether the callback triggers without
            subcommands.
        **typer_kwargs: Additional arguments forwarded to ``Typer.callback``.

    Returns:
        Callable or callback: Either the registered callback or a decorator for
        deferred registration.
    """

    decorator = callback_decorator(
        app,
        invoke_without_command=invoke_without_command,
        **typer_kwargs,
    )
    if callback is not None:
        return decorator(callback)
    return decorator


__all__ = [
    "CLIError",
    "CLILogger",
    "build_cli_logger",
    "Depends",
    "command_decorator",
    "register_command",
    "callback_decorator",
    "register_callback",
]
