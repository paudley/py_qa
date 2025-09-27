# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""SOLID-oriented lint advice builders.

This module centralises the heuristics that translate normalised diagnostics
into human-friendly, opinionated recommendations.  Callers can either rely on
``generate_advice`` directly or instantiate :class:`AdviceBuilder` for reuse in
other presentation layers such as PR summaries or SARIF emitters.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from ..annotations import AnnotationEngine


@dataclass(frozen=True)
class AdviceEntry:
    """Structured representation of a single advice line."""

    category: AdviceCategory
    body: str


class AdviceCategory(str, Enum):
    """Enumerated categories surfaced in generated advice."""

    REFACTOR_PRIORITY = "Refactor priority"
    REFACTOR = "Refactor"
    DOCUMENTATION = "Documentation"
    TYPES = "Types"
    TYPING = "Typing"
    PACKAGING = "Packaging"
    ENCAPSULATION = "Encapsulation"
    CONSTANTS = "Constants"
    LOGGING = "Logging"
    RUNTIME_SAFETY = "Runtime safety"
    TEST_HYGIENE = "Test hygiene"
    STRUCTURE = "Structure"
    INTERFACE = "Interface"
    PRIORITISE = "Prioritise"
    SOLID = "SOLID"

    def __str__(self) -> str:  # pragma: no cover - Enum str trivial
        return self.value


@dataclass(frozen=True)
class NormalizedDiagnostic:
    file: str | None
    line: int | None
    function: str
    tool: str
    code: str
    message: str

    def is_test_path(self) -> bool:
        return _is_test_path(self.file)


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


class AdviceAccumulator:
    """Collect advice entries while deduplicating repeated suggestions."""

    def __init__(self) -> None:
        self._entries: list[AdviceEntry] = []
        self._seen: set[tuple[AdviceCategory, str]] = set()

    def add(self, category: AdviceCategory, body: str) -> None:
        key = (category, body)
        if key in self._seen:
            return
        self._seen.add(key)
        self._entries.append(AdviceEntry(category=category, body=body))

    def extend(self, entries: Iterable[AdviceEntry]) -> None:
        for entry in entries:
            self.add(entry.category, entry.body)

    @property
    def entries(self) -> list[AdviceEntry]:
        return list(self._entries)


PATH_SUMMARY_LIMIT: Final[int] = 5
COMPLEXITY_SPOT_LIMIT: Final[int] = 5
DOCUMENTATION_HINT_THRESHOLD: Final[int] = 3
TYPING_HINT_THRESHOLD: Final[int] = 3
MAGIC_NUMBER_FILE_THRESHOLD: Final[int] = 2
TEST_HYGIENE_DIAGNOSTIC_THRESHOLD: Final[int] = 5
PRIORITISE_DIAGNOSTIC_THRESHOLD: Final[int] = 8


_COMPLEXITY_CODES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("pylint", "R1260"),
        ("pylint", "R0915"),
        ("ruff", "C901"),
        ("ruff", "PLR0915"),
    },
)

_DUPLICATE_HINT_CODES: Final[dict[str, frozenset[str]]] = {
    "pylint": frozenset({"R0801", "DUPLICATE-CODE"}),
    "ruff": frozenset(
        {
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
    ),
    "pyqa": frozenset({"DRY-HASH", "DRY-MESSAGE", "DRY-CLUSTER"}),
}


def _normalize_diagnostics(
    entries: Sequence[tuple[str, int, str, str, str, str]],
) -> list[NormalizedDiagnostic]:
    diagnostics: list[NormalizedDiagnostic] = []
    for file_path, line, function, tool, code, message in entries:
        normalized_file = file_path or None
        normalized_line = line if line >= 0 else None
        normalized_tool = (tool or "").lower()
        normalized_code = ("" if code == "-" else code).upper()
        diagnostics.append(
            NormalizedDiagnostic(
                file=normalized_file,
                line=normalized_line,
                function=function,
                tool=normalized_tool,
                code=normalized_code,
                message=message,
            ),
        )
    return diagnostics


def generate_advice(
    entries: Sequence[tuple[str, int, str, str, str, str]],
    annotation_engine: AnnotationEngine,
) -> list[AdviceEntry]:
    """Return SOLID-aligned guidance derived from normalised diagnostics."""
    diagnostics = _normalize_diagnostics(entries)
    accumulator = AdviceAccumulator()

    _generate_complexity_advice(diagnostics, accumulator)
    _generate_documentation_advice(diagnostics, accumulator)
    _generate_typing_advice(diagnostics, annotation_engine, accumulator)
    _generate_stub_advice(diagnostics, accumulator)
    _generate_packaging_advice(diagnostics, accumulator)
    _generate_encapsulation_advice(diagnostics, accumulator)
    _generate_magic_value_advice(diagnostics, accumulator)
    _generate_logging_advice(diagnostics, accumulator)
    _generate_runtime_assertion_advice(diagnostics, accumulator)
    _generate_test_hygiene_advice(diagnostics, accumulator)
    _generate_duplicate_code_advice(diagnostics, accumulator)
    _generate_interface_advice(diagnostics, accumulator)
    _generate_prioritise_advice(diagnostics, accumulator)

    return accumulator.entries


def _summarise_paths(paths: Sequence[str], *, limit: int = PATH_SUMMARY_LIMIT) -> str:
    if not paths:
        return ""
    shown = [path for path in paths[:limit]]
    summary = ", ".join(shown)
    remainder = len(paths) - len(shown)
    if remainder > 0:
        summary = f"{summary}, ... (+{remainder} more)"
    return summary


def _is_test_path(path: str | None) -> bool:
    if not path:
        return False
    normalized = path.replace("\\", "/")
    return any(part.startswith("test") or part == "tests" for part in normalized.split("/"))


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


def _generate_complexity_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    complexity_targets: dict[tuple[str, str], tuple[str, str]] = {}
    for diagnostic in diagnostics:
        if (diagnostic.tool, diagnostic.code) not in _COMPLEXITY_CODES:
            continue
        file_path = diagnostic.file or "this module"
        function = diagnostic.function or ""
        complexity_targets[(file_path, function)] = (file_path, function)

    if not complexity_targets:
        return

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

        def _sort_key(item: tuple[str, str, int | None, int | None]) -> tuple[int, int, str]:
            locs = item[2] if isinstance(item[2], int) else -1
            complexity_score = item[3] if isinstance(item[3], int) else -1
            return (-locs, -complexity_score, f"{item[0]}::{item[1]}")

        top_spots = sorted(hot_spots, key=_sort_key)[:COMPLEXITY_SPOT_LIMIT]
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
            accumulator.add(
                AdviceCategory.REFACTOR_PRIORITY,
                "focus on "
                + "; ".join(pieces)
                + " to restore single-responsibility boundaries before tuning the rest.",
            )

    if file_only_targets:
        summary = _summarise_paths(sorted(set(file_only_targets)))
        if summary:
            accumulator.add(
                AdviceCategory.REFACTOR,
                f"break {summary} into smaller pieces to uphold Single Responsibility and keep cyclomatic complexity in check.",
            )


def _generate_documentation_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    doc_counts: defaultdict[str, int] = defaultdict(int)
    for diagnostic in diagnostics:
        code = diagnostic.code
        if not code:
            continue
        if (
            diagnostic.tool == "ruff" and (code.startswith("D1") or code in {"D401", "D402"})
        ) or code in {"TC002", "TC003"}:
            if diagnostic.file:
                doc_counts[diagnostic.file] += 1
    doc_targets = [
        file_path
        for file_path, count in sorted(doc_counts.items(), key=lambda item: item[1], reverse=True)
        if count >= DOCUMENTATION_HINT_THRESHOLD and file_path
    ]
    if not doc_targets:
        return
    summary = _summarise_paths(doc_targets)
    if summary:
        accumulator.add(
            AdviceCategory.DOCUMENTATION,
            "add module/function docstrings in "
            + summary
            + " so collaborators can follow intent without reading every branch—Google-style docstrings are recommended for clarity and consistency.",
        )


def _generate_typing_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    annotation_engine: AnnotationEngine,
    accumulator: AdviceAccumulator,
) -> None:
    type_counts: defaultdict[str, int] = defaultdict(int)
    annotation_keywords = {"annotation", "typed", "type hint"}
    for diagnostic in diagnostics:
        code = diagnostic.code
        message_lower = diagnostic.message.lower()
        if not diagnostic.file:
            continue
        if diagnostic.tool == "ruff" and code.startswith("ANN"):
            multiplier = _infer_annotation_targets(diagnostic.message, annotation_engine)
            type_counts[diagnostic.file] += multiplier if multiplier > 0 else 1
        elif diagnostic.tool in {"mypy", "pyright"}:
            if (
                code.startswith("ARG")
                or code.startswith("VAR")
                or any(keyword in message_lower for keyword in annotation_keywords)
            ):
                multiplier = _infer_annotation_targets(diagnostic.message, annotation_engine)
                type_counts[diagnostic.file] += multiplier if multiplier > 0 else 1

    type_targets = [
        file_path
        for file_path, count in sorted(type_counts.items(), key=lambda item: item[1], reverse=True)
        if count >= TYPING_HINT_THRESHOLD
    ]
    if not type_targets:
        return
    summary = _summarise_paths(type_targets)
    if summary:
        accumulator.add(
            AdviceCategory.TYPES,
            f"introduce explicit annotations in {summary} to narrow interfaces and align with Interface Segregation.",
        )


def _generate_stub_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    stub_flags = {
        diagnostic.file
        for diagnostic in diagnostics
        if (diagnostic.file or "").endswith(".pyi")
        and diagnostic.tool == "ruff"
        and diagnostic.code.startswith("ANN")
    }
    override_flags = {
        diagnostic.file
        for diagnostic in diagnostics
        if diagnostic.tool == "pyright"
        and (
            "override" in diagnostic.message.lower()
            or diagnostic.code.startswith("REPORTINCOMPATIBLE")
            or diagnostic.code == "REPORTMETHODOVERRIDESIGNATURE"
        )
    }
    if stub_flags and override_flags:
        accumulator.add(
            AdviceCategory.TYPING,
            "align stubs with implementations—double-check stub signatures against code and update when upstream changes land.",
        )


def _generate_packaging_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    for diagnostic in diagnostics:
        if diagnostic.code == "INP001":
            target = diagnostic.file or diagnostic.message.split()[0]
            directory = str(Path(target).parent) if target else "this package"
            location = directory or "."
            accumulator.add(
                AdviceCategory.PACKAGING,
                f"add an __init__.py to {location} so imports stay predictable and tooling can locate modules.",
            )
            return


def _generate_encapsulation_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    private_codes = {"SLF001", "TID252"}
    private_keywords = {"private import", "module is internal"}
    for diagnostic in diagnostics:
        code = diagnostic.code
        message_lower = diagnostic.message.lower()
        if code in private_codes:
            accumulator.add(
                AdviceCategory.ENCAPSULATION,
                "expose public APIs instead of importing internal members; re-export what callers need.",
            )
            return
        if diagnostic.tool == "pyright" and (
            code == "REPORTPRIVATEIMPORTUSAGE"
            or any(keyword in message_lower for keyword in private_keywords)
        ):
            accumulator.add(
                AdviceCategory.ENCAPSULATION,
                "expose public APIs instead of importing internal members; re-export what callers need.",
            )
            return


def _generate_magic_value_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    magic_counts: defaultdict[str, int] = defaultdict(int)
    for diagnostic in diagnostics:
        if diagnostic.code == "PLR2004" and diagnostic.file:
            magic_counts[diagnostic.file] += 1
    magic_targets = [
        file_path
        for file_path, count in sorted(magic_counts.items(), key=lambda item: item[1], reverse=True)
        if count >= MAGIC_NUMBER_FILE_THRESHOLD
    ]
    if not magic_targets:
        return
    summary = _summarise_paths(magic_targets)
    if summary:
        accumulator.add(
            AdviceCategory.CONSTANTS,
            f"move magic numbers in {summary} into named constants or configuration objects for clarity.",
        )


def _generate_logging_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    debug_codes = {"T201", "ERA001"}
    if any(diagnostic.code in debug_codes for diagnostic in diagnostics):
        accumulator.add(
            AdviceCategory.LOGGING,
            "replace debugging prints or commented blocks with structured logging or tests before merging.",
        )


def _generate_runtime_assertion_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    for diagnostic in diagnostics:
        if diagnostic.code in {"S101", "B101"} and not diagnostic.is_test_path():
            accumulator.add(
                AdviceCategory.RUNTIME_SAFETY,
                "swap bare assert with explicit condition checks or exceptions so optimized builds keep validation.",
            )
            return


def _generate_test_hygiene_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    test_diagnostics = [diagnostic for diagnostic in diagnostics if diagnostic.is_test_path()]
    if len(test_diagnostics) >= TEST_HYGIENE_DIAGNOSTIC_THRESHOLD:
        accumulator.add(
            AdviceCategory.TEST_HYGIENE,
            "refactor noisy tests to shared helpers or fixtures and split long assertions so failures isolate quickly.",
        )


def _generate_duplicate_code_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    for diagnostic in diagnostics:
        tool_codes = _DUPLICATE_HINT_CODES.get(diagnostic.tool, set())
        if diagnostic.code in tool_codes:
            paths = _duplicate_paths(diagnostic)
            summary = _summarise_paths(paths) if paths else ""
            if summary:
                body = (
                    f"DRY up duplicate code spanning {summary} by extracting a shared helper, module, or interface."
                )
            else:
                body = "DRY up duplicate code by extracting a shared helper, module, or interface."
            accumulator.add(AdviceCategory.SOLID, body)
            return


def _generate_interface_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    for diagnostic in diagnostics:
        if diagnostic.tool in {"pyright", "mypy"} and diagnostic.code in {
            "REPORTUNDEFINEDVARIABLE",
            "ATTR-DEFINED",
            "ATTRDEFINED",
        }:
            file_path = diagnostic.file or "this module"
            accumulator.add(
                AdviceCategory.INTERFACE,
                f"reconcile module boundaries in {file_path} by defining the missing attribute or exporting it explicitly.",
            )
            return


def _generate_prioritise_advice(
    diagnostics: Sequence[NormalizedDiagnostic],
    accumulator: AdviceAccumulator,
) -> None:
    file_counter = Counter(diagnostic.file for diagnostic in diagnostics if diagnostic.file)
    if not file_counter:
        return
    file_path, count = file_counter.most_common(1)[0]
    if count >= PRIORITISE_DIAGNOSTIC_THRESHOLD:
        accumulator.add(
            AdviceCategory.PRIORITISE,
            f"focus on {file_path} first; it triggered {count} diagnostics in this run.",
        )


def _duplicate_paths(diagnostic: NormalizedDiagnostic) -> list[str]:
    matches = _DUPLICATE_LOCATION_PATTERN.search(diagnostic.message)
    if not matches:
        return [diagnostic.file] if diagnostic.file else []
    entries = [segment.strip() for segment in matches.group(1).split(";")]
    paths = []
    for entry in entries:
        if not entry:
            continue
        path = entry.split(":")[0].strip()
        if path:
            paths.append(path)
    if not paths and diagnostic.file:
        paths.append(diagnostic.file)
    return paths


__all__ = [
    "AdviceBuilder",
    "AdviceCategory",
    "AdviceEntry",
    "generate_advice",
]
_DUPLICATE_LOCATION_PATTERN = re.compile(r"\(([^()]+)\)$")
