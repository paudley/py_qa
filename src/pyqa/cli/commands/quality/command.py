# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""CLI entry points for repository quality checks."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, cast

import typer

from pyqa.cli.protocols import TyperAdapter
from pyqa.config import QualityConfigSection as QualityConfigModel

from ....compliance.quality import check_commit_message, ensure_branch_protection
from ...core.shared import CLIError, Depends, build_cli_logger, register_callback
from ...core.typer_ext import TyperAppConfig, create_typer
from .models import (
    EMOJI_OPTION,
    ROOT_OPTION,
    QualityCLIInputParams,
    QualityCLIOptions,
    build_quality_options,
)
from .rendering import render_py_qa_skip_warning, render_quality_result
from .services import (
    determine_checks,
    load_quality_context,
    render_config_warnings,
    resolve_target_files,
    run_quality_checks,
)

_QUALITY_TY = create_typer(
    config=TyperAppConfig(
        name="check-quality",
        help_text="Run repository quality checks (license headers, schema, hygiene).",
        invoke_without_command=True,
    ),
)
quality_app = TyperAdapter(_QUALITY_TY)


@register_callback(quality_app, invoke_without_command=True)
def main(
    ctx: typer.Context,
    options: Annotated[QualityCLIOptions, Depends(build_quality_options)],
) -> None:
    """Execute repository quality checks across the configured project.

    Args:
        ctx: Typer context used to detect subcommand invocations.
        options: Structured CLI inputs (root, path filters, flags) constructed by
            :func:`build_quality_options`.
    """

    if ctx.invoked_subcommand:
        return

    logger = build_cli_logger(emoji=options.emoji)
    try:
        context = load_quality_context(options, logger=logger)
    except CLIError as exc:
        raise typer.Exit(code=exc.exit_code) from exc
    render_config_warnings(context, logger=logger)

    quality_settings = cast(QualityConfigModel, context.config.quality)
    checks = determine_checks(
        available_checks=quality_settings.checks,
        requested_checks=context.options.requested_checks,
        include_schema=context.options.include_schema,
    )

    targets = resolve_target_files(context, logger=logger)
    render_py_qa_skip_warning(targets.ignored_py_qa, logger=logger)
    if targets.had_explicit_paths and targets.files is None:
        raise typer.Exit(code=0)

    result = run_quality_checks(context, files=targets.files, checks=checks)
    render_quality_result(result, root=context.root, logger=logger)
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
    """

    resolved_root = root.resolve()
    logger = build_cli_logger(emoji=emoji)
    result = check_commit_message(resolved_root, message_file)
    render_quality_result(result, root=resolved_root, logger=logger)
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
    """

    options = QualityCLIOptions.from_cli(
        QualityCLIInputParams(
            root=root,
            paths=(),
            staged=False,
            fix=False,
            requested_checks=(),
            include_schema=True,
            emoji=emoji,
        ),
    )
    logger = build_cli_logger(emoji=emoji)
    try:
        context = load_quality_context(options, logger=logger)
    except CLIError as exc:
        raise typer.Exit(code=exc.exit_code) from exc
    quality_settings = cast(QualityConfigModel, context.config.quality)

    result = ensure_branch_protection(context.root, quality_settings)
    if not result.issues:
        logger.ok("Branch check passed")
        raise typer.Exit(code=0)

    render_quality_result(result, root=context.root, logger=logger)
    raise typer.Exit(code=1)


__all__ = ["quality_app"]
