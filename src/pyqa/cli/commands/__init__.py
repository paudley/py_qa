# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI command registry."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from typer import Typer

from ...plugins import load_cli_plugins
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

__all__ = ["register_commands"]


def register_commands(
    app: Typer,
    *,
    plugins: Sequence[Callable[[Typer], None]] | None = None,
) -> None:
    """Register built-in and plugin CLI commands on ``app``.

    Args:
        app: Typer application receiving command registrations.
        plugins: Optional sequence of plugin factories to invoke. When ``None``
            entry points from ``pyqa.cli.plugins`` are loaded automatically.
    """

    lint.register(app)
    install.register(app)
    config.register(app)
    security.register(app)
    banned.register(app)
    tool_info.register(app)
    quality.register(app)
    update.register(app)
    clean.register(app)
    hooks.register(app)
    doctor.register(app)

    plugin_factories: Sequence[Callable[[Typer], None]] = plugins if plugins is not None else load_cli_plugins()
    for register_plugin in plugin_factories:
        register_plugin(app)
