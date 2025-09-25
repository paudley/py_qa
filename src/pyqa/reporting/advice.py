# SPDX-License-Identifier: MIT
"""SOLID-oriented lint advice builders.

This module centralises the heuristics that translate normalised diagnostics
into human-friendly, opinionated recommendations.  Callers can either rely on
``generate_advice`` directly or instantiate :class:`AdviceBuilder` for reuse in
other presentation layers such as PR summaries or SARIF emitters.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..annotations import AnnotationEngine

@dataclass(frozen=True)
class AdviceEntry:
    """Structured representation of a single advice line."""

    category: str
    body: str


class AdviceBuilder:
    """Reusable façade for generating advice with shared annotation state."""

    def __init__(self, annotation_engine: AnnotationEngine | None = None) -> None:
        self._engine = annotation_engine or AnnotationEngine()

    @property
    def annotation_engine(self) -> AnnotationEngine:
        """Return the underlying annotation engine (useful for cache priming)."""

        return self._engine

    def build(self, entries: Sequence[tuple[str, int, str, str, str, str]]) -> list[AdviceEntry]:
        """Generate advice entries from concise formatter tuples."""

        return generate_advice(entries, self._engine)


_COMPLEXITY_CODES = {
    ("pylint", "R1260"),
    ("pylint", "R0915"),
    ("ruff", "C901"),
    ("ruff", "PLR0915"),
}

_DUPLICATE_HINT_CODES = {
    "pylint": {"R0801"},
    "ruff": {
        "B014",
        "B025",
        "B033",
        "PIE794",
        "PIE796",
        "PYI016",
        "PYI062",
        "PT014",
        "SIM101",
        "PLE0241",
        "PLE1132",
        "PLE1310",
        "PLR0804",
    },
}


def generate_advice(
    entries: Sequence[tuple[str, int, str, str, str, str]],
    annotation_engine: AnnotationEngine,
) -> list[AdviceEntry]:
    """Return SOLID-aligned guidance derived from normalised diagnostics."""

    diagnostics = [
        {
            "file": item[0],
            "line": item[1] if item[1] >= 0 else None,
            "function": item[2],
            "tool": (item[3] or "").lower(),
            "code": ("" if item[4] == "-" else item[4]).upper(),
            "message": item[5],
        }
        for item in entries
    ]

    advice: list[AdviceEntry] = []
    seen: set[tuple[str, str]] = set()

    def add(category: str, body: str) -> None:
        key = (category, body)
        if key in seen:
            return
        seen.add(key)
        advice.append(AdviceEntry(category=category, body=body))

    def is_test_path(path: str | None) -> bool:
        if not path:
            return False
        normalized = path.replace("\\", "/")
        return any(part.startswith("test") or part == "tests" for part in normalized.split("/"))

    # Complexity hotspots
    complexity_targets: dict[tuple[str, str], tuple[str, str]] = {}
    for record in diagnostics:
        key = (record["tool"], record["code"])
        if key not in _COMPLEXITY_CODES:
            continue
        file_path = record["file"] or "this module"
        function = record["function"] or ""
        complexity_targets[(file_path, function)] = (file_path, function)

    if complexity_targets:
        function_targets: list[tuple[str, str]] = []
        file_only_targets: list[str] = []
        for file_path, function in complexity_targets.values():
            if function:
                function_targets.append((file_path, function))
            elif file_path:
                file_only_targets.append(file_path)

        if function_targets:
            hot_spots: list[tuple[str, str, int | None, int | None]] = []
            for file_path, function in function_targets:
                size, complexity = _estimate_function_scale(Path(file_path), function)
                hot_spots.append((file_path, function, size, complexity))

            def sort_key(item: tuple[str, str, int | None, int | None]) -> tuple[int, int, str]:
                locs = item[2] if isinstance(item[2], int) else -1
                compl = item[3] if isinstance(item[3], int) else -1
                return (-locs, -compl, f"{item[0]}::{item[1]}")

            top_spots = sorted(hot_spots, key=sort_key)[:5]
            if top_spots:
                pieces: list[str] = []
                for file_path, function, size, complexity in top_spots:
                    descriptor = f"function {function} in {file_path}"
                    details: list[str] = []
                    if isinstance(size, int) and size >= 0:
                        details.append(f"~{size} lines")
                    if isinstance(complexity, int) and complexity >= 0:
                        details.append(f"complexity≈{complexity}")
                    if details:
                        descriptor = f"{descriptor} ({', '.join(details)})"
                    pieces.append(descriptor)
                add(
                    "Refactor priority",
                    "focus on " + "; ".join(pieces) + " to restore single-responsibility boundaries before tuning the rest.",
                )

        if file_only_targets:
            summary = _summarise_paths(sorted(set(file_only_targets)))
            if summary:
                add(
                    "Refactor",
                    f"break {summary} into smaller pieces to uphold Single Responsibility and keep cyclomatic complexity in check.",
                )

    # Documentation gaps
    doc_counts: defaultdict[str, int] = defaultdict(int)
    for record in diagnostics:
        code = record["code"]
        if not code:
            continue
        if (
            record["tool"] == "ruff" and (code.startswith("D1") or code in {"D401", "D402"})
        ) or code in {"TC002", "TC003"}:
            doc_counts[record["file"]] += 1
    doc_targets = [
        file_path
        for file_path, count in sorted(doc_counts.items(), key=lambda item: item[1], reverse=True)
        if count >= 3 and file_path
    ]
    if doc_targets:
        summary = _summarise_paths(doc_targets)
        if summary:
            add(
                "Documentation",
                f"add module/function docstrings in {summary} so collaborators can follow intent without reading every branch—Google-style docstrings are recommended for clarity and consistency.",
            )

    # Type-annotation hygiene
    type_counts: defaultdict[str, int] = defaultdict(int)
    annotation_keywords = {"annotation", "typed", "type hint"}
    for record in diagnostics:
        code = record["code"]
        msg_lower = record["message"].lower()
        file_path = record["file"]
        if not file_path:
            continue
        if record["tool"] == "ruff" and code.startswith("ANN"):
            multiplier = _infer_annotation_targets(record["message"], annotation_engine)
            type_counts[file_path] += multiplier if multiplier > 0 else 1
        elif record["tool"] in {"mypy", "pyright"}:
            if (
                code.startswith("ARG")
                or code.startswith("VAR")
                or any(keyword in msg_lower for keyword in annotation_keywords)
            ):
                multiplier = _infer_annotation_targets(record["message"], annotation_engine)
                type_counts[file_path] += multiplier if multiplier > 0 else 1
    type_targets = [
        file_path
        for file_path, count in sorted(type_counts.items(), key=lambda item: item[1], reverse=True)
        if count >= 3
    ]
    if type_targets:
        summary = _summarise_paths(type_targets)
        if summary:
            add(
                "Types",
                f"introduce explicit annotations in {summary} to narrow interfaces and align with Interface Segregation.",
            )

    # Stub maintenance issues
    stub_flags = {
        record["file"]
        for record in diagnostics
        if (record["file"] or "").endswith(".pyi")
        and record["tool"] == "ruff"
        and record["code"].startswith("ANN")
    }
    override_flags = {
        record["file"]
        for record in diagnostics
        if record["tool"] == "pyright"
        and (
            "override" in record["message"].lower()
            or record["code"].startswith("REPORTINCOMPATIBLE")
            or record["code"] == "REPORTMETHODOVERRIDESIGNATURE"
        )
    }
    if stub_flags and override_flags:
        add(
            "Typing",
            "align stubs with implementations—double-check stub signatures against code and update when upstream changes land.",
        )

    # Implicit namespace packages
    for record in diagnostics:
        if record["code"] == "INP001":
            target = record["file"] or record["message"].split()[0]
            directory = str(Path(target).parent) if target else "this package"
            location = directory or "."
            add(
                "Packaging",
                f"add an __init__.py to {location} so imports stay predictable and tooling can locate modules.",
            )
            break

    # Private/internal imports
    private_codes = {"SLF001", "TID252"}
    private_keywords = {"private import", "module is internal"}
    for record in diagnostics:
        code = record["code"]
        message_lower = record["message"].lower()
        if code in private_codes:
            add(
                "Encapsulation",
                "expose public APIs instead of importing internal members; re-export what callers need.",
            )
            break
        if record["tool"] == "pyright" and (
            code == "REPORTPRIVATEIMPORTUSAGE"
            or any(keyword in message_lower for keyword in private_keywords)
        ):
            add(
                "Encapsulation",
                "expose public APIs instead of importing internal members; re-export what callers need.",
            )
            break

    # Magic values
    magic_counts: defaultdict[str, int] = defaultdict(int)
    for record in diagnostics:
        if record["code"] == "PLR2004" and record["file"]:
            magic_counts[record["file"]] += 1
    magic_targets = [
        file_path
        for file_path, count in sorted(magic_counts.items(), key=lambda item: item[1], reverse=True)
        if count >= 2
    ]
    if magic_targets:
        summary = _summarise_paths(magic_targets)
        if summary:
            add(
                "Constants",
                f"move magic numbers in {summary} into named constants or configuration objects for clarity.",
            )

    # Debug artifacts
    debug_codes = {"T201", "ERA001"}
    if any(record["code"] in debug_codes for record in diagnostics):
        add(
            "Logging",
            "replace debugging prints or commented blocks with structured logging or tests before merging.",
        )

    # Production assertions
    for record in diagnostics:
        if record["code"] in {"S101", "B101"} and not is_test_path(record["file"]):
            add(
                "Runtime safety",
                "swap bare assert with explicit condition checks or exceptions so optimized builds keep validation.",
            )
            break

    # Test hygiene
    test_diagnostics = [record for record in diagnostics if is_test_path(record["file"])]
    if len(test_diagnostics) >= 5:
        add(
            "Test hygiene",
            "refactor noisy tests to shared helpers or fixtures and split long assertions so failures isolate quickly.",
        )

    # Duplicate code
    duplicate_hit = False
    for record in diagnostics:
        tool_codes = _DUPLICATE_HINT_CODES.get(record["tool"], set())
        if record["code"] in tool_codes:
            duplicate_hit = True
            break
    if duplicate_hit:
        add(
            "Structure",
            "deduplicate repeated logic or declarations—extract helpers or consolidate definitions to stay Open/Closed and reduce drift.",
        )

    # Undef interfaces / attribute access across modules
    for record in diagnostics:
        if record["tool"] in {"pyright", "mypy"} and record["code"] in {
            "REPORTUNDEFINEDVARIABLE",
            "ATTR-DEFINED",
            "ATTRDEFINED",
        }:
            file_path = record["file"] or "this module"
            add(
                "Interface",
                f"reconcile module boundaries in {file_path} by defining the missing attribute or exporting it explicitly.",
            )
            break

    # Focus suggestion for highest density file
    file_counter = Counter(record["file"] for record in diagnostics if record["file"])
    if file_counter:
        file_path, count = file_counter.most_common(1)[0]
        if count >= 8:
            add(
                "Prioritise",
                f"focus on {file_path} first; it triggered {count} diagnostics in this run.",
            )

    return advice


def _summarise_paths(paths: Sequence[str], *, limit: int = 5) -> str:
    if not paths:
        return ""
    shown = [path for path in paths[:limit]]
    summary = ", ".join(shown)
    remainder = len(paths) - len(shown)
    if remainder > 0:
        summary = f"{summary}, ... (+{remainder} more)"
    return summary


def _estimate_function_scale(path: Path, function: str) -> tuple[int | None, int | None]:
    if not function:
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

    count = 1  # include signature
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


def _infer_annotation_targets(message: str, engine: AnnotationEngine) -> int:
    spans = engine.message_spans(message)
    return sum(1 for span in spans if span.style == "ansi256:213")


__all__ = [
    "AdviceBuilder",
    "AdviceEntry",
    "generate_advice",
]
