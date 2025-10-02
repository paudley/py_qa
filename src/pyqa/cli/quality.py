# SPDX-License-Identifier: MIT
"""CLI entry points for repository quality checks."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, cast

import typer

from ..config import QualityConfigSection
from ..logging import ok
from ..quality import check_commit_message, ensure_branch_protection
from .typer_ext import create_typer
from ._quality_cli_models import QualityCLIOptions
from ._quality_cli_rendering import render_py_qa_skip_warning, render_quality_result
from ._quality_cli_services import (
    build_quality_checker,
    determine_checks,
    load_quality_context,
    render_config_warnings,
    resolve_target_files,
)

ROOT_OPTION = Annotated[
    Path,
    typer.Option(Path.cwd(), "--root", "-r", help="Project root."),
]
EMOJI_OPTION = Annotated[
    bool,
    typer.Option(True, "--emoji/--no-emoji", help="Toggle emoji in output."),
]

quality_app = create_typer(
    name="check-quality",
    help="Run repository quality checks (license headers, schema, hygiene).",
    invoke_without_command=True,
)


@quality_app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    root: ROOT_OPTION,
    paths: list[Path] | None = typer.Argument(
        None,
        metavar="[PATHS...]",
        help="Optional file paths to scope the checks.",
    ),
    staged: bool = typer.Option(
        False,
        "--staged/--no-staged",
        help=(
            "Use staged files instead of discovering all tracked files when no "
            "PATHS are provided."
        ),
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Attempt to repair license notices and SPDX tags before re-running checks.",
        is_flag=True,
    ),
    check: list[str] | None = typer.Option(
        None,
        "--check",
        "-c",
        help="Limit execution to specific checks (e.g. license,file-size,schema,python).",
    ),
    no_schema: bool = typer.Option(False, "--no-schema", help="Skip schema validation."),
    emoji: EMOJI_OPTION = True,
) -> None:
    """Execute repository quality checks across the configured project.

    Args:
        ctx: Typer context used to detect subcommand invocations.
        root: Project root directory containing configuration and sources.
        paths: Optional explicit paths limiting the scope of checks.
        staged: Whether to consider only staged changes when no paths are provided.
        fix: Whether to automatically repair applicable issues before rechecking.
        check: Optional list of specific checks to run.
        no_schema: Whether to skip schema validation entirely.
        emoji: Toggle emoji output when rendering progress and results.

    Returns:
        None: The command exits via :func:`typer.Exit` after rendering results.
    """

    if ctx.invoked_subcommand:
        return

    options = QualityCLIOptions.from_cli(
        root=root,
        paths=tuple(paths or []),
        staged=staged,
        fix=fix,
        requested_checks=tuple(check or []),
        include_schema=not no_schema,
        emoji=emoji,
    )

    context = load_quality_context(options)
    render_config_warnings(context)

    quality_settings = cast(QualityConfigSection, context.config.quality)
    checks = determine_checks(
        available_checks=quality_settings.checks,
        requested_checks=context.options.requested_checks,
        include_schema=context.options.include_schema,
    )

    targets = resolve_target_files(context)
    render_py_qa_skip_warning(targets.ignored_py_qa, emoji=context.options.emoji)
    if targets.had_explicit_paths and targets.files is None:
        raise typer.Exit(code=0)

    checker = build_quality_checker(context, files=targets.files, checks=checks)
    result = checker.run(fix=context.options.fix)
    render_quality_result(result, root=context.root, use_emoji=context.options.emoji)
    raise typer.Exit(code=result.exit_code())


@quality_app.command("commit-msg")
def commit_msg(
    root: ROOT_OPTION,
    message_file: Path = typer.Argument(..., metavar="FILE", help="Commit message file."),
    emoji: EMOJI_OPTION = True,
) -> None:
    """Validate commit message quality according to repository policy.

    Args:
        root: Repository root used for configuration and ignore detection.
        message_file: Path to the commit message provided by git hooks.
        emoji: Toggle emoji output when rendering diagnostic results.

    Returns:
        None: The command exits via :func:`typer.Exit` with the check result.
    """

    resolved_root = root.resolve()
    result = check_commit_message(resolved_root, message_file)
    render_quality_result(result, root=resolved_root, use_emoji=emoji)
    raise typer.Exit(code=result.exit_code())


@quality_app.command("branch")
def branch_guard(
    root: ROOT_OPTION,
    emoji: EMOJI_OPTION = True,
) -> None:
    """Ensure protected branch policies align with repository configuration.

    Args:
        root: Repository root containing the quality configuration.
        emoji: Toggle emoji output for rendered diagnostics.

    Returns:
        None: The command exits via :func:`typer.Exit` after reporting status.
    """

    options = QualityCLIOptions.from_cli(
        root=root,
        paths=(),
        staged=False,
        fix=False,
        requested_checks=(),
        include_schema=True,
        emoji=emoji,
    )
    context = load_quality_context(options)
    quality_settings = cast(QualityConfigSection, context.config.quality)

    result = ensure_branch_protection(context.root, quality_settings)
    if not result.issues:
        ok("Branch check passed", use_emoji=emoji)
        raise typer.Exit(code=0)

    render_quality_result(result, root=context.root, use_emoji=emoji)
    raise typer.Exit(code=1)


__all__ = ["quality_app"]
