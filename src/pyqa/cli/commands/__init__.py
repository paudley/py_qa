# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI command registry."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import typer

from ...cli.protocols import TyperAdapter, TyperLike
from ...plugins import load_cli_plugins as _discover_cli_plugins
from . import (
    banned,
    clean,
    config,
    doctor,
    hooks,
    install,
    lint,
    quality,
    security,
    tool_info,
    update,
)

__all__ = ["register_commands", "load_cli_plugins"]


def load_cli_plugins() -> Sequence[Callable[[TyperLike], None]]:
    """Return CLI plugin factories discovered via entry points.

    Returns:
        Sequence[Callable[[TyperLike], None]]: Iterable of CLI plugin factories.
    """

    return _discover_cli_plugins()


def register_commands(
    app: TyperLike | typer.Typer,
    *,
    plugins: Sequence[Callable[[TyperLike], None]] | None = None,
) -> None:
    """Register built-in and plugin CLI commands on ``app``.

    Args:
        app: Typer-compatible application receiving command registrations.
        plugins: Optional sequence of plugin factories to invoke. When ``None``
            entry points from ``pyqa.cli.plugins`` are loaded automatically.
    """
    if isinstance(app, typer.Typer):
        cli_app: TyperLike = TyperAdapter(app)
    else:
        cli_app = app

    lint.register(cli_app)
    install.register(cli_app)
    config.register(cli_app)
    security.register(cli_app)
    banned.register(cli_app)
    tool_info.register(cli_app)
    quality.register(cli_app)
    update.register(cli_app)
    clean.register(cli_app)
    hooks.register(cli_app)
    doctor.register(cli_app)

    if plugins is not None:
        plugin_factories: Sequence[Callable[[TyperLike], None]] = plugins
    else:
        plugin_factories = load_cli_plugins()
    for register_plugin in plugin_factories:
        register_plugin(cli_app)
