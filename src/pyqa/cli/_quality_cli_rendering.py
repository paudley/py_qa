# SPDX-License-Identifier: MIT
"""Rendering helpers for the quality CLI commands."""

from __future__ import annotations

from pathlib import Path

from ..constants import PY_QA_DIR_NAME
from ..quality import QualityCheckResult, QualityIssueLevel
from .shared import CLILogger


def render_quality_result(
    result: QualityCheckResult,
    *,
    root: Path,
    logger: CLILogger,
) -> None:
    """Render quality check results to the terminal."""

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


def render_py_qa_skip_warning(
    ignored: tuple[str, ...],
    *,
    logger: CLILogger,
) -> None:
    """Render a warning describing py-qa directories skipped during execution."""

    if not ignored:
        return
    unique = ", ".join(ignored)
    logger.warn(
        f"Ignoring path(s) {unique}: '{PY_QA_DIR_NAME}' directories are skipped "
        "unless check-quality runs inside the py_qa workspace."
    )


def _format_issue_location(path: object | None, root: Path) -> str:
    """Return a human-readable issue location string."""

    path_obj = _to_path(path)
    if path_obj is None:
        return "" if path is None else f" [{path}]"

    try:
        relative = path_obj.resolve().relative_to(root.resolve())
        return f" [{relative}]"
    except ValueError:
        return f" [{path_obj}]"


def _to_path(value: object) -> Path | None:
    """Return ``value`` as a path when possible."""

    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    return None


__all__ = ["render_py_qa_skip_warning", "render_quality_result"]
