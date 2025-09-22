# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Console formatters for orchestrator results."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..config import OutputConfig
from ..logging import colorize, emoji
from ..models import Diagnostic, RunResult
from ..severity import Severity


def render(result: RunResult, cfg: OutputConfig) -> None:
    if cfg.quiet:
        _render_quiet(result, cfg)
        return
    match cfg.output:
        case "pretty":
            _render_pretty(result, cfg)
        case "raw":
            _render_raw(result)
        case "concise" | _:
            _render_concise(result, cfg)


def _render_concise(result: RunResult, cfg: OutputConfig) -> None:
    header = f"Ran {len(result.outcomes)} action(s) against {len(result.files)} file(s)"
    print(colorize(header, "cyan", cfg.color))
    for outcome in result.outcomes:
        status = "ok" if outcome.ok else "failed"
        symbol = {
            True: emoji("✅", cfg.emoji),
            False: emoji("❌", cfg.emoji),
        }[outcome.ok]
        print(
            f"{symbol} {outcome.tool}:{outcome.action} [{status}] rc={outcome.returncode}"
        )
        if outcome.diagnostics and cfg.show_passing:
            _dump_diagnostics(outcome.diagnostics, cfg)


def _render_quiet(result: RunResult, cfg: OutputConfig) -> None:
    failed = [outcome for outcome in result.outcomes if not outcome.ok]
    if not failed:
        print("ok")
        return
    for outcome in failed:
        print(f"{outcome.tool}:{outcome.action} failed rc={outcome.returncode}")
        if outcome.stderr:
            print(outcome.stderr.rstrip())
        if outcome.diagnostics:
            _dump_diagnostics(outcome.diagnostics, cfg)


def _render_pretty(result: RunResult, cfg: OutputConfig) -> None:
    root_display = colorize(str(Path(result.root).resolve()), "blue", cfg.color)
    print(f"Root: {root_display}")
    for outcome in result.outcomes:
        status = (
            colorize("PASS", "green", cfg.color)
            if outcome.ok
            else colorize("FAIL", "red", cfg.color)
        )
        print(f"\n{outcome.tool}:{outcome.action} — {status}")
        if outcome.stdout:
            print(colorize("stdout:", "cyan", cfg.color))
            print(outcome.stdout.rstrip())
        if outcome.stderr:
            print(colorize("stderr:", "yellow", cfg.color))
            print(outcome.stderr.rstrip())
        if outcome.diagnostics:
            print(colorize("diagnostics:", "bold", cfg.color))
            _dump_diagnostics(outcome.diagnostics, cfg)


def _render_raw(result: RunResult) -> None:
    for outcome in result.outcomes:
        print(outcome.stdout.rstrip())
        if outcome.stderr:
            print(outcome.stderr.rstrip())


def _dump_diagnostics(diags: Iterable[Diagnostic], cfg: OutputConfig) -> None:
    for diag in diags:
        location = ""
        if diag.file:
            suffix = ""
            if diag.line is not None:
                suffix = f":{diag.line}"
                if diag.column is not None:
                    suffix += f":{diag.column}"
            location = f"{diag.file}{suffix}"
        sev_color = _severity_color(diag.severity)
        sev_display = colorize(diag.severity.value, sev_color, cfg.color)
        code_display = f" [{diag.code}]" if diag.code else ""
        print(f"  {sev_display} {location} {diag.message}{code_display}")


def _severity_color(sev: Severity) -> str:
    return {
        Severity.ERROR: "red",
        Severity.WARNING: "yellow",
        Severity.NOTICE: "blue",
        Severity.NOTE: "cyan",
    }.get(sev, "yellow")
