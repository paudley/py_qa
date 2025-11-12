# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Rendering helpers for the quality CLI commands."""

from __future__ import annotations

from pathlib import Path

from pyqa.core.config.constants import PYQA_LINT_DIR_NAME

from ....compliance.quality import QualityCheckResult, QualityIssueLevel
from ...core.shared import CLILogger


def render_quality_result(
    result: QualityCheckResult,
    *,
    root: Path,
    logger: CLILogger,
) -> None:
    """Render quality check results to the terminal.

    Args:
        result: Structured quality check outcome containing issues to report.
        root: Workspace root used for normalising issue paths.
        logger: CLI logger responsible for user-facing messaging.

    The function produces console output describing quality issues.
    """

    if not result.issues:
        logger.ok("Quality checks passed")
        return

    for issue in result.issues:
        location = _format_issue_location(issue.path, root)
        message = f"{issue.message}{location}"
        if issue.level is QualityIssueLevel.ERROR:
            logger.fail(message)
        else:
            logger.warn(message)

    summary = (
        f"Quality checks failed with {len(result.errors)} error(s)"
        if result.errors
        else f"Quality checks completed with {len(result.warnings)} warning(s)"
    )
    if result.errors:
        logger.fail(summary)
    else:
        logger.warn(summary)


def render_pyqa_lint_skip_warning(
    ignored: tuple[str, ...],
    *,
    logger: CLILogger,
) -> None:
    """Render a warning describing pyqa_lint directories skipped during execution.

    Args:
        ignored: Tuple of directory names filtered during processing.
        logger: CLI logger used to surface the warning to the user.

    Emits a warning to the provided logger when directories are ignored.
    """

    if not ignored:
        return
    unique = ", ".join(ignored)
    logger.warn(
        f"Ignoring path(s) {unique}: '{PYQA_LINT_DIR_NAME}' directories are skipped "
        "unless check-quality runs inside the pyqa_lint workspace."
    )


def _format_issue_location(path: str | Path | None, root: Path) -> str:
    """Return a human-readable issue location string.

    Args:
        path: Raw location provided by the quality issue.
        root: Workspace root used to normalise relative paths.

    Returns:
        str: Human-readable location suffix suitable for console output.
    """

    path_obj = _to_path(path)
    if path_obj is None:
        return "" if path is None else f" [{path}]"
    relative = _relative_path_or_original(path_obj, root)
    return f" [{relative}]"


def _to_path(value: str | Path | None) -> Path | None:
    """Return ``value`` as a path when possible.

    Args:
        value: Raw representation to convert into a path.

    Returns:
        Path | None: Normalised path when conversion succeeds, otherwise ``None``.
    """

    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    return None


def _relative_path_or_original(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` when both share a common prefix.

    Args:
        path: Filesystem path associated with the diagnostic.
        root: Workspace root used to normalise diagnostic paths.

    Returns:
        str: ``path`` relative to ``root`` when possible, otherwise the
        absolute representation of ``path``.
    """

    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        return str(resolved_path.relative_to(resolved_root))
    except ValueError:
        return str(path)


__all__ = ["render_pyqa_lint_skip_warning", "render_quality_result"]
