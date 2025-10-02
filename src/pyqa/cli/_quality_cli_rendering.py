# SPDX-License-Identifier: MIT
"""Rendering helpers for the quality CLI commands."""

from __future__ import annotations

from pathlib import Path

from ..constants import PY_QA_DIR_NAME
from ..logging import fail, ok, warn
from ..quality import QualityCheckResult, QualityIssueLevel


def render_quality_result(
    result: QualityCheckResult,
    *,
    root: Path,
    use_emoji: bool,
) -> None:
    """Render quality check results to the terminal."""

    if not result.issues:
        ok("Quality checks passed", use_emoji=use_emoji)
        return

    for issue in result.issues:
        prefix = fail if issue.level is QualityIssueLevel.ERROR else warn
        location = _format_issue_location(issue.path, root)
        prefix(f"{issue.message}{location}", use_emoji=use_emoji)

    summary = (
        f"Quality checks failed with {len(result.errors)} error(s)"
        if result.errors
        else f"Quality checks completed with {len(result.warnings)} warning(s)"
    )
    reporter = fail if result.errors else warn
    reporter(summary, use_emoji=use_emoji)


def render_py_qa_skip_warning(
    ignored: tuple[str, ...],
    *,
    emoji: bool,
) -> None:
    """Render a warning describing py-qa directories skipped during execution."""

    if not ignored:
        return
    unique = ", ".join(ignored)
    warn(
        (
            f"Ignoring path(s) {unique}: '{PY_QA_DIR_NAME}' directories are skipped "
            "unless check-quality runs inside the py_qa workspace."
        ),
        use_emoji=emoji,
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
