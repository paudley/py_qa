# SPDX-License-Identifier: MIT
"""Helper services used by the quality CLI commands."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Final

from ..constants import PY_QA_DIR_NAME
from ..quality import QualityChecker, QualityCheckerOptions
from ..workspace import is_py_qa_workspace
from ._config_loading import load_config_result
from ._quality_cli_models import (
    QualityCLIOptions,
    QualityConfigContext,
    QualityTargetResolution,
)
from .shared import CLILogger
from .utils import filter_py_qa_paths


def load_quality_context(
    options: QualityCLIOptions,
    *,
    logger: CLILogger,
) -> QualityConfigContext:
    """Load project configuration and return a populated context.

    Args:
        options: Normalized CLI options describing the requested run.
        logger: CLI logger used to surface loading errors to the user.

    Returns:
        QualityConfigContext: Loaded configuration and deferred warnings.

    Raises:
        CLIError: Raised when configuration loading fails.
    """

    load_result = load_config_result(options.root, logger=logger)

    context = QualityConfigContext(
        root=options.root,
        config=load_result.config,
        options=options,
        warnings=tuple(load_result.warnings),
    )
    _apply_workspace_protections(context)
    return context


def render_config_warnings(context: QualityConfigContext, *, logger: CLILogger) -> None:
    """Emit configuration warnings gathered during loading.

    Args:
        context: Loaded quality configuration context containing warnings to
            present to the user.
        logger: CLI logger used to emit the warning text.
    """

    for message in context.warnings:
        logger.warn(message)


def determine_checks(
    *,
    available_checks: Iterable[str],
    requested_checks: Iterable[str],
    include_schema: bool,
) -> frozenset[str]:
    """Return the set of checks to execute based on CLI input.

    Args:
        available_checks: Default checks defined by the configuration.
        requested_checks: Optional user-provided subset of checks.
        include_schema: Indicates whether schema validation is allowed.

    Returns:
        frozenset[str]: Final set of checks to execute.
    """

    selected = set(requested_checks or available_checks)
    if not include_schema and SCHEMA_CHECK in selected:
        selected.remove(SCHEMA_CHECK)
    return frozenset(selected)


def resolve_target_files(
    context: QualityConfigContext,
    *,
    logger: CLILogger,
) -> QualityTargetResolution:
    """Return filtered target files and ignored py-qa paths.

    Args:
        context: Loaded configuration context containing CLI options.
        logger: CLI logger used to emit informational messages when no files
            are selected for quality checks.

    Returns:
        QualityTargetResolution: Files that should be checked and a record of
        ignored py-qa paths for reporting.
    """

    provided = list(context.options.raw_paths)
    resolved = [path if path.is_absolute() else (context.root / path) for path in provided]
    kept, ignored = filter_py_qa_paths(resolved, context.root)
    files = kept or None
    if provided and not kept:
        logger.ok("No files to check.")
    return QualityTargetResolution(
        files=files,
        ignored_py_qa=tuple(dict.fromkeys(ignored)),
        had_explicit_paths=bool(provided),
    )


def build_quality_checker(
    context: QualityConfigContext,
    *,
    files: list[Path] | None,
    checks: frozenset[str],
) -> QualityChecker:
    """Construct the quality checker for execution.

    Args:
        context: Loaded configuration context describing the project state.
        files: Optional list of explicit files to process.
        checks: Set of checks selected for the run.

    Returns:
        QualityChecker: Prepared checker instance ready for execution.
    """

    return QualityChecker(
        root=context.root,
        quality=context.config.quality,
        options=QualityCheckerOptions(
            license_overrides=context.config.license,
            files=files,
            checks=checks,
            staged=context.options.staged,
        ),
    )


def _apply_workspace_protections(context: QualityConfigContext) -> None:
    """Ensure py-qa paths are skipped outside the workspace.

    Args:
        context: Loaded configuration context whose quality and license
            sections will be mutated in place when outside the workspace.
    """

    if is_py_qa_workspace(context.root):
        return

    extra_skip = f"{PY_QA_DIR_NAME}/**"
    quality_config = context.config.quality
    license_config = context.config.license

    if extra_skip not in quality_config.skip_globs:
        quality_config.skip_globs.append(extra_skip)
    if extra_skip not in license_config.exceptions:
        license_config.exceptions.append(extra_skip)


__all__ = [
    "build_quality_checker",
    "determine_checks",
    "load_quality_context",
    "render_config_warnings",
    "resolve_target_files",
]
SCHEMA_CHECK: Final[str] = "schema"
