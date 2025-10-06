# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Specialised renderers for quiet, pretty, and raw output modes."""

from __future__ import annotations

from pathlib import Path

from ...config import OutputConfig
from ...logging import colorize
from ...models import RunResult
from .diagnostics import dump_diagnostics, join_output


def render_quiet_mode(result: RunResult, cfg: OutputConfig) -> None:
    """Render diagnostics in quiet mode."""

    failed = [outcome for outcome in result.outcomes if not outcome.ok]
    if not failed:
        print("ok")
        return
    for outcome in failed:
        print(f"{outcome.tool}:{outcome.action} failed rc={outcome.returncode}")
        if outcome.stderr:
            print(join_output(outcome.stderr).rstrip())
        if outcome.diagnostics:
            dump_diagnostics(outcome.diagnostics, cfg)


def render_pretty_mode(result: RunResult, cfg: OutputConfig) -> None:
    """Render orchestrator results in a human-friendly pretty format."""

    root_display = colorize(str(Path(result.root).resolve()), "blue", cfg.color)
    print(f"Root: {root_display}")
    for outcome in result.outcomes:
        status = colorize("PASS", "green", cfg.color) if outcome.ok else colorize("FAIL", "red", cfg.color)
        print(f"\n{outcome.tool}:{outcome.action} — {status}")
        if outcome.stdout:
            print(colorize("stdout:", "cyan", cfg.color))
            print(join_output(outcome.stdout).rstrip())
        if outcome.stderr:
            print(colorize("stderr:", "yellow", cfg.color))
            print(join_output(outcome.stderr).rstrip())
        if outcome.diagnostics:
            print(colorize("diagnostics:", "bold", cfg.color))
            dump_diagnostics(outcome.diagnostics, cfg)

    if result.outcomes:
        print()


def render_raw_mode(result: RunResult) -> None:
    """Render orchestrator stdout/stderr streams without additional formatting."""

    for outcome in result.outcomes:
        print(join_output(outcome.stdout).rstrip())
        if outcome.stderr:
            print(join_output(outcome.stderr).rstrip())


__all__ = [
    "render_pretty_mode",
    "render_quiet_mode",
    "render_raw_mode",
]
