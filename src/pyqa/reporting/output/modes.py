# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Specialised renderers for quiet, pretty, and raw output modes."""

from __future__ import annotations

from pathlib import Path

from ...config import OutputConfig
from ...core.logging import colorize
from ...core.models import RunResult
from ...runtime.console.manager import get_console_manager
from .diagnostics import dump_diagnostics, join_output


def render_quiet_mode(result: RunResult, cfg: OutputConfig) -> None:
    """Render diagnostics in quiet mode.

    Args:
        result: Run result produced by the orchestrator.
        cfg: Output configuration controlling colour/emoji usage.
    """

    console = get_console_manager().get(color=cfg.color, emoji=cfg.emoji)
    failed = [outcome for outcome in result.outcomes if not outcome.ok]
    if not failed:
        console.print("ok")
        return
    for outcome in failed:
        console.print(f"{outcome.tool}:{outcome.action} failed rc={outcome.returncode}")
        if outcome.stderr:
            console.print(join_output(outcome.stderr).rstrip())
        if outcome.diagnostics:
            dump_diagnostics(outcome.diagnostics, cfg)


def render_pretty_mode(result: RunResult, cfg: OutputConfig) -> None:
    """Render orchestrator results in a human-friendly pretty format.

    Args:
        result: Run result produced by the orchestrator.
        cfg: Output configuration controlling formatting options.
    """

    root_display = colorize(str(Path(result.root).resolve()), "blue", cfg.color)
    console = get_console_manager().get(color=cfg.color, emoji=cfg.emoji)
    console.print(f"Root: {root_display}")
    for outcome in result.outcomes:
        status = colorize("PASS", "green", cfg.color) if outcome.ok else colorize("FAIL", "red", cfg.color)
        console.print(f"\n{outcome.tool}:{outcome.action} — {status}")
        if outcome.stdout:
            console.print(colorize("stdout:", "cyan", cfg.color))
            console.print(join_output(outcome.stdout).rstrip())
        if outcome.stderr:
            console.print(colorize("stderr:", "yellow", cfg.color))
            console.print(join_output(outcome.stderr).rstrip())
        if outcome.diagnostics:
            console.print(colorize("diagnostics:", "bold", cfg.color))
            dump_diagnostics(outcome.diagnostics, cfg)

    if result.outcomes:
        console.print()


def render_raw_mode(result: RunResult) -> None:
    """Render orchestrator stdout/stderr streams without additional formatting.

    Args:
        result: Run result produced by the orchestrator.
    """

    console = get_console_manager().get(color=False, emoji=False)
    for outcome in result.outcomes:
        console.print(join_output(outcome.stdout).rstrip())
        if outcome.stderr:
            console.print(join_output(outcome.stderr).rstrip())


__all__ = [
    "render_pretty_mode",
    "render_quiet_mode",
    "render_raw_mode",
]
