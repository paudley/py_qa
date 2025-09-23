# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI entry points for repository quality checks."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from ..config_loader import ConfigError, ConfigLoader
from ..logging import fail, ok, warn
from ..quality import (
    QualityChecker,
    QualityCheckResult,
    QualityIssueLevel,
    check_commit_message,
    ensure_branch_protection,
)

quality_app = typer.Typer(
    name="check-quality",
    help="Run repository quality checks (license headers, schema, hygiene).",
    invoke_without_command=True,
)


@quality_app.callback()
def main(
    ctx: typer.Context,
    paths: List[Path] | None = typer.Argument(
        None, metavar="[PATHS...]", help="Optional file paths to scope the checks."
    ),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    staged: bool = typer.Option(
        False,
        "--staged/--no-staged",
        help="Use staged files instead of discovering all tracked files when no PATHS are provided.",
    ),
    check: Optional[List[str]] = typer.Option(
        None,
        "--check",
        "-c",
        help="Limit execution to specific checks (e.g. license,file-size,schema,python).",
    ),
    no_schema: bool = typer.Option(
        False, "--no-schema", help="Skip schema validation."
    ),
    emoji: bool = typer.Option(
        True, "--emoji/--no-emoji", help="Toggle emoji in output."
    ),
) -> None:
    if ctx.invoked_subcommand:
        return

    loader = ConfigLoader.for_root(root)
    try:
        load_result = loader.load_with_trace()
    except ConfigError as exc:
        fail(f"Configuration invalid: {exc}", use_emoji=emoji)
        raise typer.Exit(code=1) from exc

    config = load_result.config
    for warning in load_result.warnings:
        warn(warning, use_emoji=emoji)

    selected_checks = set(check or config.quality.checks)
    if no_schema and "schema" in selected_checks:
        selected_checks.remove("schema")

    files = list(paths or []) or None

    checker = QualityChecker(
        root=root,
        quality=config.quality,
        license_overrides=config.license,
        files=files,
        checks=selected_checks,
        staged=staged,
    )
    result = checker.run()
    _render_result(result, root, emoji)
    raise typer.Exit(code=result.exit_code())


@quality_app.command("commit-msg")
def commit_msg(
    message_file: Path = typer.Argument(
        ..., metavar="FILE", help="Commit message file."
    ),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    emoji: bool = typer.Option(
        True, "--emoji/--no-emoji", help="Toggle emoji in output."
    ),
) -> None:
    result = check_commit_message(root, message_file)
    _render_result(result, root, emoji)
    raise typer.Exit(code=result.exit_code())


@quality_app.command("branch")
def branch_guard(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
    emoji: bool = typer.Option(
        True, "--emoji/--no-emoji", help="Toggle emoji in output."
    ),
) -> None:
    loader = ConfigLoader.for_root(root)
    try:
        load_result = loader.load_with_trace()
    except ConfigError as exc:
        fail(f"Configuration invalid: {exc}", use_emoji=emoji)
        raise typer.Exit(code=1) from exc

    result = ensure_branch_protection(root, load_result.config.quality)
    if not result.issues:
        ok("Branch check passed", use_emoji=emoji)
        raise typer.Exit(code=0)
    _render_result(result, root, emoji)
    raise typer.Exit(code=1)


def _render_result(result: QualityCheckResult, root: Path, use_emoji: bool) -> None:
    if not result.issues:
        ok("Quality checks passed", use_emoji=use_emoji)
        return

    for issue in result.issues:
        prefix = fail if issue.level is QualityIssueLevel.ERROR else warn
        location = ""
        if issue.path is not None:
            path_obj = _to_path(issue.path)
            if path_obj is not None:
                try:
                    relative = path_obj.resolve().relative_to(root.resolve())
                    location = f" [{relative}]"
                except ValueError:
                    location = f" [{path_obj}]"
            else:
                location = f" [{issue.path}]"
        prefix(f"{issue.message}{location}", use_emoji=use_emoji)

    if result.errors:
        fail(
            f"Quality checks failed with {len(result.errors)} error(s)",
            use_emoji=use_emoji,
        )
    else:
        warn(
            f"Quality checks completed with {len(result.warnings)} warning(s)",
            use_emoji=use_emoji,
        )


def _to_path(value: object) -> Path | None:
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    return None


__all__ = ["quality_app"]
