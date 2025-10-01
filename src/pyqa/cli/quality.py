# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI entry points for repository quality checks."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..config_loader import ConfigError, ConfigLoader
from ..constants import PY_QA_DIR_NAME
from ..logging import fail, ok, warn
from ..quality import (
    QualityChecker,
    QualityCheckerOptions,
    QualityCheckResult,
    QualityIssueLevel,
    check_commit_message,
    ensure_branch_protection,
)
from ..workspace import is_py_qa_workspace
from .typer_ext import create_typer
from .utils import filter_py_qa_paths

ROOT_OPTION = Annotated[Path, typer.Option(Path.cwd(), "--root", "-r", help="Project root.")]
EMOJI_OPTION = Annotated[bool, typer.Option(True, "--emoji/--no-emoji", help="Toggle emoji in output.")]

quality_app = create_typer(
    name="check-quality",
    help="Run repository quality checks (license headers, schema, hygiene).",
    invoke_without_command=True,
)


@quality_app.callback()
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
        help="Use staged files instead of discovering all tracked files when no PATHS are provided.",
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

    root = root.resolve()
    loader = ConfigLoader.for_root(root)
    try:
        load_result = loader.load_with_trace()
    except ConfigError as exc:
        fail(f"Configuration invalid: {exc}", use_emoji=emoji)
        raise typer.Exit(code=1) from exc

    config = load_result.config
    quality_config = config.quality
    license_config = config.license
    if not is_py_qa_workspace(root):
        extra_skip = f"{PY_QA_DIR_NAME}/**"
        if extra_skip not in quality_config.skip_globs:
            quality_config.skip_globs.append(extra_skip)
        if extra_skip not in license_config.exceptions:
            license_config.exceptions.append(extra_skip)
    for warning in load_result.warnings:
        warn(warning, use_emoji=emoji)

    selected_checks = set(check or config.quality.checks)
    if no_schema and "schema" in selected_checks:
        selected_checks.remove("schema")

    provided_paths = list(paths or [])
    resolved_explicit = [path if path.is_absolute() else (root / path) for path in provided_paths]
    kept_paths, ignored_py_qa = filter_py_qa_paths(resolved_explicit, root)
    if ignored_py_qa:
        unique = ", ".join(dict.fromkeys(ignored_py_qa))
        warn(
            (
                f"Ignoring path(s) {unique}: '{PY_QA_DIR_NAME}' directories are skipped "
                "unless check-quality runs inside the py_qa workspace."
            ),
            use_emoji=emoji,
        )
    if provided_paths and not kept_paths:
        ok("No files to check.", use_emoji=emoji)
        raise typer.Exit(code=0)
    files = kept_paths or None

    checker = QualityChecker(
        root=root,
        quality=config.quality,
        options=QualityCheckerOptions(
            license_overrides=config.license,
            files=files,
            checks=selected_checks,
            staged=staged,
        ),
    )
    result = checker.run(fix=fix)
    _render_result(result, root, emoji)
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

    result = check_commit_message(root, message_file)
    _render_result(result, root, emoji)
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
