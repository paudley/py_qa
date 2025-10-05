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
from functools import lru_cache
from pathlib import Path
from typing import Final

from ..annotations import AnnotationEngine
from ..filesystem.paths import normalize_path
from ..tools.catalog_metadata import catalog_duplicate_hint_codes


class AdviceCategory(str, Enum):
    """Enumerate advice categories surfaced to users."""

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

    def __str__(self) -> str:  # pragma: no cover - trivial
        """Return the human-readable category label."""

        return self.value


@dataclass(frozen=True)
class AdviceEntry:
    """Structured representation of a single advice line."""

    category: AdviceCategory
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


MIN_DOC_FINDINGS: Final[int] = 3
MIN_TYPE_FINDINGS: Final[int] = 3
MIN_MAGIC_OCCURRENCES: Final[int] = 2
FOCUS_THRESHOLD: Final[int] = 8
MISSING_LINE_SENTINEL: Final[int] = -1
MISSING_CODE_SENTINEL: Final[str] = "-"
MIN_TEST_HYGIENE_DIAGNOSTICS: Final[int] = 5
MAX_COMPLEXITY_SUMMARIES: Final[int] = 5
TEST_TOKENS: Final[tuple[str, ...]] = ("tests",)
COMPLEXITY_CODES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("pylint", "R1260"),
        ("pylint", "R0915"),
        ("ruff", "C901"),
        ("ruff", "PLR0915"),
    },
)
DOC_RUFF_CODES: Final[frozenset[str]] = frozenset({"D401", "D402"})
PRIVATE_IMPORT_CODES: Final[frozenset[str]] = frozenset({"SLF001", "TID252"})
PYRIGHT_PRIVATE_IMPORT_CODE: Final[str] = "REPORTPRIVATEIMPORTUSAGE"
DEBUG_CODES: Final[frozenset[str]] = frozenset({"T201", "ERA001"})
ASSERT_CODES: Final[frozenset[str]] = frozenset({"S101", "B101"})
MAGIC_NUMBER_CODE: Final[str] = "PLR2004"
ANNOTATION_KEYWORDS: Final[frozenset[str]] = frozenset({"annotation", "typed", "type hint"})
RUFF_TOOL: Final[str] = "ruff"
PYRIGHT_TOOL: Final[str] = "pyright"
MYPY_TOOL: Final[str] = "mypy"
PYLINT_TOOL: Final[str] = "pylint"
INHERITANCE_OVERRIDE_CODE: Final[str] = "REPORTMETHODOVERRIDESIGNATURE"
STUB_OVERRIDE_LABEL: Final[str] = "override"
IMP_NAMESPACE_CODE: Final[str] = "INP001"


@dataclass(frozen=True)
class DiagnosticRecord:
    """Normalised diagnostic fields used for advice synthesis."""

    file_path: str | None
    line: int | None
    function: str | None
    tool: str
    code: str
    message: str


class _AdviceAccumulator:
    """Accumulator that deduplicates advice entries before emission."""

    def __init__(self, annotation_engine: AnnotationEngine) -> None:
        self._annotation_engine = annotation_engine
        self._seen: set[tuple[AdviceCategory, str]] = set()
        self._entries: list[AdviceEntry] = []

    @property
    def annotation_engine(self) -> AnnotationEngine:
        """Return the annotation engine used for message parsing."""

        return self._annotation_engine

    @property
    def entries(self) -> list[AdviceEntry]:
        """Return the accumulated advice entries."""

        return list(self._entries)

    def add(self, category: AdviceCategory, body: str) -> None:
        """Append an advice entry when not already emitted."""

        key = (category, body)
        if key in self._seen:
            return
        self._seen.add(key)
        self._entries.append(AdviceEntry(category=category, body=body))


def generate_advice(
    entries: Sequence[tuple[str, int, str, str, str, str]],
    annotation_engine: AnnotationEngine,
) -> list[AdviceEntry]:
    """Return SOLID-aligned guidance derived from normalised diagnostics.

    Args:
        entries: Sequence of diagnostic tuples in the canonical formatter
            shape ``(file, line, function, tool, code, message)``.  ``line`` is
            expected to be ``-1`` when unavailable, while blank codes are marked
            with ``-``.
        annotation_engine: Shared annotation engine capable of highlighting
            message spans used for weighting annotation-related advice.

    Returns:
        list[AdviceEntry]: Ordered list of unique advice entries reflecting the
        supplied diagnostics.

    """

    diagnostics = _normalise_entries(entries)
    accumulator = _AdviceAccumulator(annotation_engine)

    _append_complexity_guidance(accumulator, diagnostics)
    _append_documentation_guidance(accumulator, diagnostics)
    _append_annotation_guidance(accumulator, diagnostics)
    _append_stub_guidance(accumulator, diagnostics)
    _append_packaging_guidance(accumulator, diagnostics)
    _append_encapsulation_guidance(accumulator, diagnostics)
    _append_magic_number_guidance(accumulator, diagnostics)
    _append_debug_guidance(accumulator, diagnostics)
    _append_runtime_assertion_guidance(accumulator, diagnostics)
    _append_test_guidance(accumulator, diagnostics)
    _append_duplicate_guidance(accumulator, diagnostics)
    _append_interface_guidance(accumulator, diagnostics)
    _append_focus_guidance(accumulator, diagnostics)

    return accumulator.entries


def _normalise_entries(
    entries: Sequence[tuple[str, int, str, str, str, str]],
) -> list[DiagnosticRecord]:
    """Return normalised diagnostic records derived from formatter tuples."""

    records: list[DiagnosticRecord] = []
    for file_path, line, function, tool, code, message in entries:
        normalised_line = line if line != MISSING_LINE_SENTINEL else None
        normalised_tool = (tool or "").lower()
        normalised_code = "" if code == MISSING_CODE_SENTINEL else code.upper()
        record = DiagnosticRecord(
            file_path=file_path or None,
            line=normalised_line,
            function=function or None,
            tool=normalised_tool,
            code=normalised_code,
            message=message or "",
        )
        records.append(record)
    return records


def _append_complexity_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Highlight complexity hotspots by function and file."""

    function_targets, file_targets = _collect_complexity_targets(diagnostics)
    _append_function_complexity_guidance(accumulator, function_targets)
    _append_file_complexity_guidance(accumulator, file_targets)


def _collect_complexity_targets(
    diagnostics: Sequence[DiagnosticRecord],
) -> tuple[list[tuple[str, str]], set[str]]:
    """Return complexity targets grouped by function and file."""

    function_targets: list[tuple[str, str]] = []
    file_targets: set[str] = set()
    seen: set[tuple[str, str]] = set()
    for record in diagnostics:
        if (record.tool, record.code) not in COMPLEXITY_CODES:
            continue
        file_path = record.file_path or "this module"
        function = record.function or ""
        key = (file_path, function)
        if key in seen:
            continue
        seen.add(key)
        if function:
            function_targets.append(key)
        else:
            file_targets.add(file_path)
    return function_targets, file_targets


def _append_function_complexity_guidance(
    accumulator: _AdviceAccumulator,
    function_targets: Sequence[tuple[str, str]],
) -> None:
    """Add refactor priority advice for complex functions."""

    if not function_targets:
        return

    hotspots: list[tuple[str, str, int | None, int | None]] = []
    for file_path, function in function_targets:
        size, complexity = _estimate_function_scale(Path(file_path), function)
        hotspots.append((file_path, function, size, complexity))

    def sort_key(item: tuple[str, str, int | None, int | None]) -> tuple[int, int, str]:
        locs = item[2] if isinstance(item[2], int) else -1
        complexity = item[3] if isinstance(item[3], int) else -1
        return (-locs, -complexity, f"{item[0]}::{item[1]}")

    top_spots = sorted(hotspots, key=sort_key)[:MAX_COMPLEXITY_SUMMARIES]
    if not top_spots:
        return

    descriptors: list[str] = []
    for file_path, function, size, complexity in top_spots:
        descriptor = f"function {function} in {file_path}"
        details: list[str] = []
        if isinstance(size, int) and size >= 0:
            details.append(f"~{size} lines")
        if isinstance(complexity, int) and complexity >= 0:
            details.append(f"complexity≈{complexity}")
        if details:
            descriptor = f"{descriptor} ({', '.join(details)})"
        descriptors.append(descriptor)

    accumulator.add(
        AdviceCategory.REFACTOR_PRIORITY,
        ("focus on " + "; ".join(descriptors) + " to restore single-responsibility boundaries before tuning the rest."),
    )


def _append_file_complexity_guidance(
    accumulator: _AdviceAccumulator,
    file_targets: Iterable[str],
) -> None:
    """Add advice for files flagged by complexity heuristics."""

    unique_targets = sorted(set(file_targets))
    if not unique_targets:
        return
    summary = _summarise_paths(unique_targets)
    if not summary:
        return
    accumulator.add(
        AdviceCategory.REFACTOR,
        ("break " + summary + " into smaller, single-purpose modules so complexity stays low."),
    )


def _append_documentation_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Surface documentation nudges when doc warnings pile up."""

    counts: defaultdict[str, int] = defaultdict(int)
    for record in diagnostics:
        if not record.code or not record.file_path:
            continue
        if record.tool == RUFF_TOOL and (record.code.startswith("D1") or record.code in DOC_RUFF_CODES):
            counts[record.file_path] += 1
        elif record.code in {"TC002", "TC003"}:
            counts[record.file_path] += 1

    doc_targets = [
        file_path
        for file_path, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        if count >= MIN_DOC_FINDINGS
    ]
    if not doc_targets:
        return

    summary = _summarise_paths(doc_targets)
    if summary:
        accumulator.add(
            AdviceCategory.DOCUMENTATION,
            (
                f"add module/function docstrings in {summary} "
                "so collaborators follow intent without scanning every branch—"
                "Google-style docstrings keep narratives consistent."
            ),
        )


def _append_annotation_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Encourage stronger typing based on annotation-related diagnostics."""

    counts: defaultdict[str, int] = defaultdict(int)
    engine = accumulator.annotation_engine
    for record in diagnostics:
        if not record.file_path:
            continue
        if record.tool == RUFF_TOOL and record.code.startswith("ANN"):
            multiplier = _infer_annotation_targets(record.message, engine)
            counts[record.file_path] += multiplier if multiplier > 0 else 1
            continue
        if record.tool in {MYPY_TOOL, PYRIGHT_TOOL}:
            code = record.code
            message_lower = record.message.lower()
            if (
                code.startswith("ARG")
                or code.startswith("VAR")
                or any(keyword in message_lower for keyword in ANNOTATION_KEYWORDS)
            ):
                multiplier = _infer_annotation_targets(record.message, engine)
                counts[record.file_path] += multiplier if multiplier > 0 else 1

    targets = [
        file_path
        for file_path, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        if count >= MIN_TYPE_FINDINGS
    ]
    if not targets:
        return

    summary = _summarise_paths(targets)
    if summary:
        accumulator.add(
            AdviceCategory.TYPES,
            (f"introduce explicit annotations in {summary} to narrow interfaces and satisfy Interface Segregation."),
        )


def _append_stub_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Nudge teams to align stubs with implementations when inconsistent."""

    stub_files = {
        record.file_path
        for record in diagnostics
        if (
            record.file_path
            and record.file_path.endswith(".pyi")
            and record.tool == RUFF_TOOL
            and record.code.startswith("ANN")
        )
    }
    override_files = {
        record.file_path
        for record in diagnostics
        if (
            record.tool == PYRIGHT_TOOL
            and record.file_path
            and (
                STUB_OVERRIDE_LABEL in record.message.lower()
                or record.code.startswith("REPORTINCOMPATIBLE")
                or record.code == INHERITANCE_OVERRIDE_CODE
            )
        )
    }
    if stub_files and override_files:
        accumulator.add(
            AdviceCategory.TYPING,
            "Align stubs with implementations—keep signatures in sync as upstream changes land.",
        )


def _append_packaging_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Recommend adding namespace packages where missing."""

    for record in diagnostics:
        if record.code != IMP_NAMESPACE_CODE:
            continue
        target = record.file_path or record.message.split()[0]
        location = str(Path(target).parent) if target else "this package"
        location = location or "."
        accumulator.add(
            AdviceCategory.PACKAGING,
            f"Add an __init__.py to {location} so imports stay predictable and tooling can locate modules.",
        )
        break


def _append_encapsulation_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Flag private import usage across tools."""

    private_keywords = {"private import", "module is internal"}
    for record in diagnostics:
        if record.code in PRIVATE_IMPORT_CODES:
            accumulator.add(
                AdviceCategory.ENCAPSULATION,
                "Expose public APIs instead of importing internal members; re-export the pieces callers need.",
            )
            return
        if record.tool == PYRIGHT_TOOL and (
            record.code == PYRIGHT_PRIVATE_IMPORT_CODE
            or any(keyword in record.message.lower() for keyword in private_keywords)
        ):
            accumulator.add(
                AdviceCategory.ENCAPSULATION,
                "Expose public APIs instead of importing internal members; re-export the pieces callers need.",
            )
            return


def _append_magic_number_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Encourage extracting repeated magic numbers."""

    counts: defaultdict[str, int] = defaultdict(int)
    for record in diagnostics:
        if record.code == MAGIC_NUMBER_CODE and record.file_path:
            counts[record.file_path] += 1
    targets = [
        file_path
        for file_path, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        if count >= MIN_MAGIC_OCCURRENCES
    ]
    if not targets:
        return
    summary = _summarise_paths(targets)
    if summary:
        accumulator.add(
            AdviceCategory.CONSTANTS,
            f"Move magic numbers in {summary} into named constants or configuration objects for clarity.",
        )


def _append_debug_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Remind teams to strip debugging artefacts before merging."""

    if any(record.code in DEBUG_CODES for record in diagnostics):
        accumulator.add(
            AdviceCategory.LOGGING,
            "Replace debugging prints or commented blocks with structured logging or tests before merging.",
        )


def _append_runtime_assertion_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Discourage production asserts outside test suites."""

    for record in diagnostics:
        if record.code in ASSERT_CODES and not _is_test_path(record.file_path):
            accumulator.add(
                AdviceCategory.RUNTIME_SAFETY,
                "Swap bare assert with explicit checks or exceptions to keep optimized builds safe.",
            )
            return


def _append_test_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Surface test hygiene advice when noisy suites dominate."""

    test_diagnostics = [record for record in diagnostics if _is_test_path(record.file_path)]
    if len(test_diagnostics) >= MIN_TEST_HYGIENE_DIAGNOSTICS:
        accumulator.add(
            AdviceCategory.TEST_HYGIENE,
            "Refactor noisy tests to shared helpers or fixtures and split long assertions so failures isolate quickly.",
        )


def _append_duplicate_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Encourage deduplication when catalog hints flag duplicates."""

    duplicate_codes = _duplicate_hint_code_map()
    for record in diagnostics:
        tool_codes = duplicate_codes.get(record.tool, set())
        if record.code and record.code in tool_codes:
            accumulator.add(
                AdviceCategory.STRUCTURE,
                (
                    "deduplicate repeated logic or declarations—extract helpers or consolidate"
                    " definitions to reduce drift while staying Open/Closed."
                ),
            )
            return


def _append_interface_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Highlight undefined interfaces reported by type checkers."""

    for record in diagnostics:
        if record.tool in {PYRIGHT_TOOL, MYPY_TOOL} and record.code in {
            "REPORTUNDEFINEDVARIABLE",
            "ATTR-DEFINED",
            "ATTRDEFINED",
        }:
            file_path = record.file_path or "this module"
            accumulator.add(
                AdviceCategory.INTERFACE,
                (f"reconcile module boundaries in {file_path}; define the missing attribute or export it."),
            )
            return


def _append_focus_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Identify high-density diagnostic files to direct focus."""

    counter = Counter(record.file_path for record in diagnostics if record.file_path)
    if not counter:
        return
    file_path, count = counter.most_common(1)[0]
    if count < FOCUS_THRESHOLD:
        return
    accumulator.add(
        AdviceCategory.PRIORITISE,
        f"focus on {file_path} first; it triggered {count} diagnostics in this run.",
    )


def _is_test_path(path: str | None) -> bool:
    """Return ``True`` when ``path`` belongs to a test directory."""

    if not path:
        return False
    try:
        normalised = normalize_path(path)
    except (ValueError, OSError):
        normalised = Path(path)
    parts = [part.lower() for part in normalised.parts]
    return any(part.startswith("test") or part in TEST_TOKENS for part in parts)


@lru_cache(maxsize=1)
def _duplicate_hint_code_map() -> dict[str, set[str]]:
    """Return catalog-backed duplicate hint codes with fallback defaults.

    Returns:
        dict[str, set[str]]: Mapping of tool identifiers to diagnostic codes that
        indicate duplicate findings.

    """
    catalog_codes = catalog_duplicate_hint_codes()
    return {tool.lower(): {code.upper() for code in codes} for tool, codes in catalog_codes.items()}


def _summarise_paths(paths: Sequence[str], *, limit: int = 5) -> str:
    """Return a human-readable summary of the provided paths."""

    if not paths:
        return ""
    shown = list(paths[:limit])
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


ANNOTATION_SPAN_STYLE: Final[str] = "ansi256:213"


def _infer_annotation_targets(message: str, engine: AnnotationEngine) -> int:
    """Return the number of highlighted annotation spans within *message*."""

    spans = engine.message_spans(message)
    return sum(1 for span in spans if span.style == ANNOTATION_SPAN_STYLE)


__all__ = [
    "AdviceBuilder",
    "AdviceEntry",
    "generate_advice",
]
