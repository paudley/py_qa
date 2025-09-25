# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Assemble a refactor navigator from diagnostics."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

from ..annotations import AnnotationEngine
from ..models import Diagnostic, RunResult


def build_refactor_navigator(result: RunResult, engine: AnnotationEngine) -> None:
    """Populate ``result.analysis['refactor_navigator']`` with hotspot data."""

    hotspots: dict[tuple[str, str], dict[str, object]] = defaultdict(  # type: ignore[var-annotated]
        lambda: {
            "file": "",
            "function": "",
            "issue_tags": defaultdict(int),
            "size": None,
            "complexity": None,
            "diagnostics": [],
        },
    )

    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            tag = _issue_tag(diag, engine)
            if tag:
                diag.tags = tuple(sorted({*diag.tags, tag}))
            key = ((diag.file or ""), diag.function or "")
            bucket = hotspots[key]
            bucket["file"] = diag.file or ""
            bucket["function"] = diag.function or ""
            if tag:
                bucket["issue_tags"][tag] += 1  # type: ignore[index]
            bucket["diagnostics"].append(
                {
                    "tool": diag.tool,
                    "code": diag.code or "",
                    "message": diag.message,
                    "line": diag.line,
                    "severity": diag.severity.value,
                },
            )

    summary: list[dict[str, object]] = []
    for (file_path, function), data in hotspots.items():
        issues = data["issue_tags"]  # type: ignore[assignment]
        if not issues:
            continue
        size, complexity = _estimate_function_scale(Path(result.root) / file_path, function)
        data["size"] = size
        data["complexity"] = complexity
        data["issue_tags"] = dict(issues)
        summary.append(data)

    summary.sort(
        key=lambda item: (
            -sum(item["issue_tags"].values()),
            (item["size"] or 0) * -1,
            f"{item['file']}::{item['function']}",
        ),
    )
    result.analysis["refactor_navigator"] = summary[:10]


def _issue_tag(diag: Diagnostic, engine: AnnotationEngine) -> str | None:
    code = (diag.code or "").upper()
    signature = set(engine.message_signature(diag.message))

    if code in {"C901", "R0915", "PLR0915", "R1260"} or {
        "complex",
        "complexity",
        "statement",
    } & signature:
        return "complexity"
    if code.startswith("ANN") or "annotation" in signature or "typed" in signature:
        return "typing"
    if "docstring" in signature or code.startswith("D1"):
        return "documentation"
    if code in {"PLR2004", "R2004"} or "magic" in signature:
        return "magic-number"
    return None


def _estimate_function_scale(path: Path, function: str) -> tuple[int | None, int | None]:
    if not function or not path.is_file():
        return (None, None)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return (None, None)
    lines = text.splitlines()
    signature_pattern = re.compile(rf"^\s*(?:async\s+)?def\s+{re.escape(function)}\b")
    start_index: int | None = None
    indent_level: int | None = None
    for idx, line in enumerate(lines):
        if signature_pattern.match(line):
            start_index = idx
            indent_level = len(line) - len(line.lstrip(" \t"))
            break
    if start_index is None or indent_level is None:
        return (None, None)

    count = 1
    complexity = 0
    keywords = re.compile(r"\b(if|for|while|elif|case|except|and|or|try|with)\b")
    for line in lines[start_index + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        current_indent = len(line) - len(line.lstrip(" \t"))
        if current_indent <= indent_level:
            break
        count += 1
        complexity += len(keywords.findall(stripped))
    return (count if count else None, complexity if complexity else None)


__all__ = ["build_refactor_navigator"]
