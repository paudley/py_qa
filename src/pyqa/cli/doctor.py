# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""System diagnostics helpers for pyqa."""

from __future__ import annotations

import importlib
import platform
import shutil
import subprocess
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.rule import Rule
from rich.table import Table

from ..config import Config, ConfigError
from ..config_loader import ConfigLoader
from ..context import TreeSitterContextResolver
from ..tools.registry import DEFAULT_REGISTRY
from .utils import ToolStatus, check_tool_status


@dataclass(slots=True)
class EnvironmentCheck:
    """Represents the outcome of a doctor environment probe."""

    name: str
    status: str
    ok: bool
    detail: str


@dataclass(slots=True)
class ToolSummary:
    """Summarised tooling availability for doctor output."""

    status: ToolStatus
    runtime: str
    default_enabled: bool
    has_override: bool


@dataclass(slots=True)
class GrammarStatus:
    """Availability information for Tree-sitter grammars."""

    language: str
    module: str
    available: bool
    version: str | None


def run_doctor(root: Path, *, console: Console | None = None) -> int:
    """Run diagnostic checks and return an exit status (0 healthy, 1 otherwise)."""

    console = console or Console()
    console.print(Rule("[bold cyan]pyqa Doctor[/bold cyan]"))

    loader = ConfigLoader.for_root(root)
    try:
        load_result = loader.load_with_trace()
    except ConfigError as exc:  # pragma: no cover - defensive, surfaced to user
        console.print(
            Panel(f"[red]Failed to load configuration:[/red] {exc}", title="Configuration", border_style="red")
        )
        return 1

    config = load_result.config

    # Environment checks
    environment_table = Table(title="Environment", box=box.SIMPLE, expand=True)
    environment_table.add_column("Check", style="bold")
    environment_table.add_column("Status", style="bold")
    environment_table.add_column("Details", overflow="fold")

    env_checks = _collect_environment_checks()
    for check in env_checks:
        status_style = "green" if check.ok else "red"
        environment_table.add_row(check.name, f"[{status_style}]{check.status}[/]", check.detail or "-")

    console.print(environment_table)

    grammar_statuses = _collect_grammar_statuses()
    if grammar_statuses:
        grammar_table = Table(title="Tree-sitter Grammars", box=box.SIMPLE, expand=True)
        grammar_table.add_column("Language", style="bold")
        grammar_table.add_column("Module")
        grammar_table.add_column("Status")
        grammar_table.add_column("Version")
        for grammar in grammar_statuses:
            style = "green" if grammar.available else "red"
            state = "available" if grammar.available else "missing"
            grammar_table.add_row(
                grammar.language,
                grammar.module,
                f"[{style}]{state}[/]",
                grammar.version or "-",
            )
        console.print(grammar_table)

    # Configuration overrides and warnings
    if load_result.warnings:
        warning_panel = Panel(
            Pretty(load_result.warnings),
            title="Configuration Warnings",
            border_style="yellow",
        )
        console.print(warning_panel)

    if load_result.updates:
        overrides_table = Table(title="Configuration Overrides", box=box.SIMPLE, expand=True)
        overrides_table.add_column("Section", style="bold")
        overrides_table.add_column("Field")
        overrides_table.add_column("Source")
        overrides_table.add_column("Value", overflow="fold")
        for update in load_result.updates:
            pretty_value = Pretty(update.value)
            overrides_table.add_row(update.section, str(update.field), update.source, pretty_value)
        console.print(overrides_table)
    else:
        console.print(Panel("[green]No configuration overrides detected.[/green]", title="Configuration"))

    # Tooling status
    tool_summaries = _collect_tool_summaries(config)
    tool_table = Table(title="Tooling Status", box=box.SIMPLE, expand=True)
    tool_table.add_column("Tool", style="bold")
    tool_table.add_column("Runtime")
    tool_table.add_column("Default")
    tool_table.add_column("Status")
    tool_table.add_column("Version")
    tool_table.add_column("Min")
    tool_table.add_column("Notes", overflow="fold")

    unhealthy = False
    for summary in tool_summaries:
        status = summary.status
        style = {
            "ok": "green",
            "vendored": "cyan",
            "outdated": "yellow",
            "unknown": "yellow",
            "not ok": "red",
            "uninstalled": "red",
        }.get(status.status, "red" if status.status else "yellow")
        if status.status in {"not ok", "uninstalled"}:
            unhealthy = True
        default_label = "yes" if summary.default_enabled else "no"
        if summary.has_override:
            default_label += "*"
        version = status.version or "-"
        min_version = status.min_version or "-"
        tool_table.add_row(
            status.name,
            summary.runtime,
            default_label,
            f"[{style}]{status.status}[/]",
            version,
            min_version,
            status.notes or "-",
        )

    console.print(tool_table)

    overall_style = "green" if not unhealthy else "red"
    console.print(
        Panel(
            f"[{overall_style}]Doctor completed[/]",
            border_style=overall_style,
        )
    )

    return 1 if unhealthy else 0


def _collect_environment_checks() -> list[EnvironmentCheck]:
    checks: list[EnvironmentCheck] = []
    checks.append(
        EnvironmentCheck(
            name="Python",
            status="ok",
            ok=True,
            detail=platform.python_version(),
        )
    )
    checks.extend(
        _probe_program(name, required)
        for name, required in [
            ("uv", True),
            ("git", True),
            ("npm", False),
            ("node", False),
            ("go", False),
            ("cargo", False),
            ("rustup", False),
            ("perl", False),
            ("cpanm", False),
        ]
    )
    checks.append(_probe_module("tree_sitter_languages", optional=False))
    checks.append(_probe_module("tree_sitter", optional=True))
    return checks


def _probe_program(executable: str, required: bool) -> EnvironmentCheck:
    path = shutil.which(executable)
    if path:
        version = _capture_version(executable)
        detail = version or path
        return EnvironmentCheck(name=executable, status="ok", ok=True, detail=detail)
    status = "missing" if required else "missing (optional)"
    return EnvironmentCheck(name=executable, status=status, ok=not required, detail="Not found in PATH")


def _probe_module(module: str, optional: bool) -> EnvironmentCheck:
    try:
        importlib.import_module(module)
    except Exception as exc:  # pragma: no cover - depends on host environment
        status = "missing" if optional else "not ok"
        detail = f"{type(exc).__name__}: {exc}"
        return EnvironmentCheck(name=module, status=status, ok=optional, detail=detail)
    return EnvironmentCheck(name=module, status="ok", ok=True, detail="Import successful")


def _collect_tool_summaries(config: Config) -> list[ToolSummary]:
    summaries: list[ToolSummary] = []
    overrides = set(config.tool_settings.keys())
    for tool in sorted(DEFAULT_REGISTRY.tools(), key=lambda item: item.name):
        status = check_tool_status(tool)
        summary = ToolSummary(
            status=status,
            runtime=tool.runtime,
            default_enabled=tool.default_enabled,
            has_override=tool.name in overrides,
        )
        summaries.append(summary)
    return summaries


def _collect_grammar_statuses() -> list[GrammarStatus]:
    resolver = TreeSitterContextResolver()
    statuses: list[GrammarStatus] = []
    for language, grammar in sorted(resolver._GRAMMAR_NAMES.items()):  # pylint: disable=protected-access
        module_name = f"tree_sitter_{grammar.replace('-', '_')}"
        try:
            module = importlib.import_module(module_name)
            available = True
            version = _grammar_version(module_name, module)
        except ModuleNotFoundError:
            available = False
            version = None
        statuses.append(GrammarStatus(language=language, module=module_name, available=available, version=version))
    return statuses


def _grammar_version(module_name: str, module: object) -> str | None:
    dist_name = module_name.replace("_", "-")
    try:
        return importlib_metadata.version(dist_name)
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover - best effort metadata lookup
        return getattr(module, "__version__", None)


def _capture_version(executable: str) -> str | None:
    for candidate in (
        [executable, "--version"],
        [executable, "-V"],
        [executable, "version"],
    ):
        try:
            completed = subprocess.run(  # nosec B603 - controlled diagnostics
                candidate,
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, ValueError):
            continue
        output = completed.stdout.strip() or completed.stderr.strip()
        if output:
            first_line = output.splitlines()[0]
            return first_line
    return None


__all__ = ["run_doctor", "EnvironmentCheck", "ToolSummary", "GrammarStatus"]
