# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Estimate change-impact scores for diagnostics based on Git diffs."""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Final

from ..context import TreeSitterContextResolver
from ..models import Diagnostic, RunResult

_DIFF_HEADER: Final[re.Pattern[str]] = re.compile(r"^\+\+\+ b/(.*)$")
_HUNK_HEADER: Final[re.Pattern[str]] = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_NEAR_CHANGE_RADIUS: Final[int] = 3
_DEV_NULL_SENTINEL: Final[str] = "/dev/null"


def apply_change_impact(result: RunResult) -> None:
    """Attach impact metadata to diagnostics inside ``result``.

    Args:
        result: Run outcome containing diagnostics to enrich.
    """
    changes = _collect_changed_lines(result.root)
    if not changes:
        return

    resolver = TreeSitterContextResolver()
    changed_functions: dict[str, set[str]] = {}
    for file_path, lines in changes.items():
        contexts = resolver.resolve_context_for_lines(
            file_path,
            root=result.root,
            lines=lines,
        )
        changed_functions[file_path] = {ctx for ctx in contexts.values() if ctx}

    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            impact = _classify_impact(diag, changes, changed_functions)
            if impact:
                diag.meta["impact"] = impact


def _classify_impact(
    diag: Diagnostic,
    changes: dict[str, set[int]],
    changed_functions: dict[str, set[str]],
) -> str | None:
    """Return the impact classification for ``diag``.

    Args:
        diag: Diagnostic under consideration.
        changes: Mapping of file paths to changed line numbers.
        changed_functions: Mapping of file paths to functions touched by the diff.

    Returns:
        str | None: Impact label when applicable.
    """

    file_path = (diag.file or "").replace("\\", "/")
    if not file_path:
        return None
    touched_lines = changes.get(file_path)
    if not touched_lines:
        return None

    if diag.line is not None:
        if diag.line in touched_lines:
            return "direct-change"
        if any(abs(diag.line - line) <= _NEAR_CHANGE_RADIUS for line in touched_lines):
            return "near-change"

    function = diag.function or ""
    if function and function in changed_functions.get(file_path, set()):
        return "function-change"

    return "stale"


def _collect_changed_lines(root: Path) -> dict[str, set[int]]:
    """Return a mapping of files to changed line numbers from Git diff output.

    Args:
        root: Repository root directory used for diff execution.

    Returns:
        dict[str, set[int]]: Changed line numbers keyed by file path.
    """

    try:
        completed = subprocess.run(
            ["git", "diff", "--unified=0", "--no-color"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError):
        return {}

    if completed.returncode not in {0, 1}:
        return {}

    file_path: str | None = None
    lines: dict[str, set[int]] = defaultdict(set)
    for raw_line in completed.stdout.splitlines():
        if not raw_line:
            continue
        header = _DIFF_HEADER.match(raw_line)
        if header:
            candidate = header.group(1)
            if candidate == _DEV_NULL_SENTINEL:
                file_path = None
            else:
                file_path = candidate
            continue
        hunk = _HUNK_HEADER.match(raw_line)
        if hunk and file_path:
            start = int(hunk.group(1)) if hunk.group(1) else 0
            length = int(hunk.group(2)) if hunk.group(2) else 1
            for offset in range(max(length, 1)):
                lines[file_path].add(start + offset)
    return {path: data for path, data in lines.items() if data}


__all__ = ["apply_change_impact"]
