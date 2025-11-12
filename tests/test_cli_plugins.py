# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests covering CLI plugin registration."""

from __future__ import annotations

import importlib

import typer
from typer.testing import CliRunner

from pyqa.cli.commands import register_commands
from pyqa.cli.protocols import TyperLike


def test_register_commands_invokes_cli_plugins(monkeypatch) -> None:
    """Registering commands should invoke plugin factories provided."""

    app = typer.Typer()
    runner = CliRunner()
    calls: list[str] = []

    def plugin_factory(cli_app: TyperLike) -> None:
        @cli_app.command("custom")
        def _custom() -> None:  # pragma: no cover - CLI side effect
            calls.append("invoked")
            typer.echo("plugin command")

    register_commands(app, plugins=(plugin_factory,))

    result = runner.invoke(app, ["custom"])
    assert result.exit_code == 0
    assert "plugin command" in result.stdout
    assert calls == ["invoked"]


def test_app_loads_entry_point_plugins(monkeypatch) -> None:
    """The top-level CLI should load CLI plugins from entry points."""

    from pyqa.cli import commands

    app_invocations: list[str] = []

    def plugin_factory(cli_app: TyperLike) -> None:
        @cli_app.command("ep")
        def _entry_point() -> None:  # pragma: no cover - CLI side effect
            app_invocations.append("ep")
            typer.echo("entry point")

    monkeypatch.setattr(commands, "load_cli_plugins", lambda: (plugin_factory,))

    # Reload the CLI app module so the patched loader is used during registration.
    app_module = importlib.reload(importlib.import_module("pyqa.cli.app"))

    runner = CliRunner()
    result = runner.invoke(app_module.app, ["ep"])
    assert result.exit_code == 0
    assert "entry point" in result.stdout
    assert app_invocations == ["ep"]

    # Restore the default command registration for subsequent tests.
    monkeypatch.setattr(commands, "load_cli_plugins", lambda: ())
    importlib.reload(app_module)
