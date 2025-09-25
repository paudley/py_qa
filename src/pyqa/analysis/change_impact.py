# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Estimate change-impact scores for diagnostics based on Git diffs."""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from ..context import TreeSitterContextResolver
from ..models import Diagnostic, RunResult

_DIFF_HEADER = re.compile(r"^\+\+\+ b/(.*)$")
_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def apply_change_impact(result: RunResult) -> None:
    """Attach impact metadata to diagnostics inside ``result``."""

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
    file_path = (diag.file or "").replace("\\", "/")
    if not file_path:
        return None
    touched_lines = changes.get(file_path)
    if not touched_lines:
        return None

    if diag.line is not None:
        if diag.line in touched_lines:
            return "direct-change"
        if any(abs(diag.line - line) <= 3 for line in touched_lines):
            return "near-change"

    function = diag.function or ""
    if function and function in changed_functions.get(file_path, set()):
        return "function-change"

    return "stale"


def _collect_changed_lines(root: Path) -> dict[str, set[int]]:
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
            if candidate == "/dev/null":
                file_path = None
            else:
                file_path = candidate
            continue
        hunk = _HUNK_HEADER.match(raw_line)
        if hunk and file_path:
            start = int(hunk.group(1)) if hunk.group(1) else 0
            length = int(hunk.group(2)) if hunk.group(2) else 1
            for offset in range(length or 1):
                lines[file_path].add(start + offset)
    return {path: data for path, data in lines.items() if data}


__all__ = ["apply_change_impact"]
