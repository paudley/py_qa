# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""SOLID-oriented lint advice builders.

This module centralises the heuristics that translate normalised diagnostics
into human-friendly, opinionated recommendations.  Callers can either rely on
``generate_advice`` directly or instantiate :class:`AdviceBuilder` for reuse in
other presentation layers such as PR summaries or SARIF emitters.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pyqa.cache.in_memory import memoize

from ...analysis.providers import NullAnnotationProvider
from ...analysis.services import resolve_function_scale_estimator
from ...catalog.metadata import catalog_duplicate_hint_codes
from ...filesystem.paths import normalize_path
from ...interfaces.analysis import AnnotationProvider, FunctionScaleEstimator

if TYPE_CHECKING:  # pragma: no cover - types only
    pass


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
        """Return the human-readable category label.

        Returns:
            str: Friendly label exposed to downstream consumers.
        """

        return self.value


@dataclass(frozen=True)
class AdviceEntry:
    """Structured representation of a single advice line."""

    category: AdviceCategory
    body: str


class AdviceBuilder:
    """Reusable façade for generating advice with shared annotation state."""

    def __init__(
        self,
        *,
        annotation_engine: AnnotationProvider | None = None,
        function_scale_estimator: FunctionScaleEstimator | None = None,
    ) -> None:
        """Create an advice builder with optional annotation and scale providers.

        Args:
            annotation_engine: Annotation provider used to enrich diagnostic context.
            function_scale_estimator: Optional estimator that supplies function scale
                metrics for prioritising complexity-related advice.
        """

        self._engine: AnnotationProvider = annotation_engine or _create_default_annotation_provider()
        self._function_scale: FunctionScaleEstimator = function_scale_estimator or resolve_function_scale_estimator()

    @property
    def annotation_engine(self) -> AnnotationProvider:
        """Return the underlying annotation provider (useful for cache priming).

        Returns:
            AnnotationProvider: Provider used to analyse message content.
        """
        return self._engine

    def build(self, entries: Sequence[tuple[str, int, str, str, str, str]]) -> list[AdviceEntry]:
        """Return advice entries derived from formatter tuples.

        Args:
            entries: Sequence of tuples matching ``generate_advice`` input shape.

        Returns:
            list[AdviceEntry]: Advice entries materialised from ``entries``.
        """

        return generate_advice(entries, self._engine, self._function_scale)


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
PYQA_DI_TOOL: Final[str] = "pyqa-di"
PYQA_DI_CODE: Final[str] = "PYQA:DI"
PYQA_DI_ALLOWED_ROOTS: Final[tuple[str, ...]] = (
    "pyqa.core.runtime.di",
    "pyqa.analysis.bootstrap",
)
PYQA_DI_ALLOWED_SUFFIX: Final[str] = ".bootstrap"
PYTHON_HYGIENE_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "python-hygiene",
        "pyqa-python-hygiene",
    }
)
PYTHON_HYGIENE_PRINT_SUFFIX: Final[str] = "PYTHON-HYGIENE:PRINT"
PYTHON_HYGIENE_SYSTEM_EXIT_SUFFIX: Final[str] = "PYTHON-HYGIENE:SYSTEM-EXIT"
PYQA_INTERFACES_TOOL: Final[str] = "pyqa-interfaces"
PYQA_INTERFACES_CODE: Final[str] = "PYQA:INTERFACES"


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

    def __init__(self, annotation_engine: AnnotationProvider) -> None:
        """Create an accumulator bound to an annotation engine.

        Args:
            annotation_engine: Engine used to extract annotation metadata.
        """
        self._annotation_engine = annotation_engine
        self._seen: set[tuple[AdviceCategory, str]] = set()
        self._entries: list[AdviceEntry] = []

    @property
    def annotation_engine(self) -> AnnotationProvider:
        """Return the annotation engine used for message parsing.

        Returns:
            AnnotationProvider: Engine leveraged while generating advice.
        """

        return self._annotation_engine

    @property
    def entries(self) -> list[AdviceEntry]:
        """Return the accumulated advice entries.

        Returns:
            list[AdviceEntry]: Copy of advice entries accumulated so far.
        """

        return list(self._entries)

    def add(self, category: AdviceCategory, body: str) -> None:
        """Append an advice entry when not already emitted.

        Args:
            category: Advice category to associate with the entry.
            body: Human-readable recommendation text.
        """

        key = (category, body)
        if key in self._seen:
            return
        self._seen.add(key)
        self._entries.append(AdviceEntry(category=category, body=body))


def generate_advice(
    entries: Sequence[tuple[str, int, str, str, str, str]],
    annotation_engine: AnnotationProvider,
    function_scale: FunctionScaleEstimator | None = None,
) -> list[AdviceEntry]:
    """Return SOLID-aligned guidance derived from normalised diagnostics.

    Args:
        entries: Sequence of diagnostic tuples in the canonical formatter
            shape ``(file, line, function, tool, code, message)``.  ``line`` is
            expected to be ``-1`` when unavailable, while blank codes are marked
            with ``-``.
        annotation_engine: Shared annotation engine capable of highlighting
            message spans used for weighting annotation-related advice.
        function_scale: Optional estimator used to determine function size and
            complexity metrics for complexity guidance. When ``None`` the
            registered service implementation is resolved.

    Returns:
        list[AdviceEntry]: Ordered list of unique advice entries reflecting the
        supplied diagnostics.

    """

    diagnostics = _normalise_entries(entries)
    accumulator = _AdviceAccumulator(annotation_engine)
    estimator = function_scale or resolve_function_scale_estimator()

    _append_complexity_guidance(accumulator, diagnostics, estimator)
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
    _append_di_guidance(accumulator, diagnostics)
    _append_interfaces_guidance(accumulator, diagnostics)
    _append_python_hygiene_guidance(accumulator, diagnostics)
    _append_interface_guidance(accumulator, diagnostics)
    _append_focus_guidance(accumulator, diagnostics)

    return accumulator.entries


def _normalise_entries(
    entries: Sequence[tuple[str, int, str, str, str, str]],
) -> list[DiagnosticRecord]:
    """Return normalised diagnostic records derived from formatter tuples.

    Args:
        entries: Raw diagnostic tuples supplied by the formatter pipeline.

    Returns:
        list[DiagnosticRecord]: Normalised diagnostic representations.
    """

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
    estimator: FunctionScaleEstimator,
) -> None:
    """Highlight complexity hotspots by function and file.

    Args:
        accumulator: Collector that records emitted advice.
        diagnostics: Diagnostic records extracted from tool output.
        estimator: Function scale estimator used to rank complexity.
    """

    function_targets, file_targets = _collect_complexity_targets(diagnostics)
    _append_function_complexity_guidance(accumulator, function_targets, estimator)
    _append_file_complexity_guidance(accumulator, file_targets)


def _collect_complexity_targets(
    diagnostics: Sequence[DiagnosticRecord],
) -> tuple[list[tuple[str, str]], set[str]]:
    """Return complexity targets grouped by function and file.

    Args:
        diagnostics: Diagnostic records gathered from complexity tools.

    Returns:
        tuple[list[tuple[str, str]], set[str]]: Function targets paired with
        file paths and a set of files requiring complexity attention.
    """

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
    estimator: FunctionScaleEstimator,
) -> None:
    """Add refactor priority advice for complex functions.

    Args:
        accumulator: Collector receiving generated advice entries.
        function_targets: Functions identified as complexity hotspots.
        estimator: Function scale estimator that supplies size metrics.
    """

    if not function_targets:
        return

    hotspots: list[tuple[str, str, int | None, int | None]] = []
    for file_path, function in function_targets:
        size, complexity = estimator.estimate(Path(file_path), function)
        hotspots.append((file_path, function, size, complexity))

    def sort_key(item: tuple[str, str, int | None, int | None]) -> tuple[int, int, str]:
        """Return a sort key prioritising largest functions and complexity.

        Args:
            item: Tuple describing the candidate function hotspot.

        Returns:
            tuple[int, int, str]: Sort key ordering by size, complexity, and identity.
        """

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
    """Add advice for files flagged by complexity heuristics.

    Args:
        accumulator: Collector receiving generated advice entries.
        file_targets: Collection of files that exceed complexity thresholds.
    """

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
    """Surface documentation nudges when doc warnings pile up.

    Args:
        accumulator: Collector receiving documentation advice entries.
        diagnostics: Diagnostic records emitted by documentation linters.
    """

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
    """Encourage stronger typing based on annotation-related diagnostics.

    Args:
        accumulator: Collector receiving type-related advice entries.
        diagnostics: Diagnostic records containing annotation findings.
    """

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
    """Nudge teams to align stubs with implementations when inconsistent.

    Args:
        accumulator: Collector receiving stub-alignment advice.
        diagnostics: Diagnostic records that include stub mismatches.
    """

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
    """Recommend adding namespace packages where missing.

    Args:
        accumulator: Collector receiving packaging-related advice.
        diagnostics: Diagnostic records highlighting namespace issues.
    """

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
    """Flag private import usage across tools.

    Args:
        accumulator: Collector that records encapsulation advice entries.
        diagnostics: Diagnostic records noting private import usage.
    """

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
    """Encourage extracting repeated magic numbers.

    Args:
        accumulator: Collector receiving advice about constants.
        diagnostics: Diagnostic records that flag magic number usage.
    """

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
    """Remind teams to strip debugging artefacts before merging.

    Args:
        accumulator: Collector receiving logging-related advice.
        diagnostics: Diagnostic records that include debug artefacts.
    """

    if any(record.code in DEBUG_CODES for record in diagnostics):
        accumulator.add(
            AdviceCategory.LOGGING,
            "Replace debugging prints or commented blocks with structured logging or tests before merging.",
        )


def _append_runtime_assertion_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Discourage production asserts outside test suites.

    Args:
        accumulator: Collector receiving runtime safety advice.
        diagnostics: Diagnostic records surfacing assert misuse.
    """

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
    """Surface test hygiene advice when noisy suites dominate.

    Args:
        accumulator: Collector receiving test hygiene advice entries.
        diagnostics: Diagnostic records captured from test-focused tools.
    """

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
    """Encourage deduplication when catalog hints flag duplicates.

    Args:
        accumulator: Collector receiving structural advice entries.
        diagnostics: Diagnostic records referencing duplicate findings.
    """

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


def _append_di_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Encourage DI wiring to remain inside approved composition roots.

    Args:
        accumulator: Collector receiving structure-related advice entries.
        diagnostics: Diagnostic records referencing DI boundary violations.
    """

    includes_di = any(record.tool == PYQA_DI_TOOL or record.code == PYQA_DI_CODE for record in diagnostics)
    if not includes_di:
        return
    allowed = ", ".join((*PYQA_DI_ALLOWED_ROOTS, f"*{PYQA_DI_ALLOWED_SUFFIX}"))
    accumulator.add(
        AdviceCategory.STRUCTURE,
        (
            "Keep dependency injection registration inside the approved composition roots "
            f"({allowed}) to preserve SOLID boundaries; relocate container wiring into those modules, "
            "use `pyqa.app.di.configure_services` or update `pyqa.di.CompositionRegistry` when a new root is "
            "justified, and rely on the DI test fixtures instead of ad-hoc registrations when exercising services."
        ),
    )


def _append_interfaces_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Promote clean interfaces-only modules when pyqa-interface finds concrete code.

    Args:
        accumulator: Collector receiving interface-focused advice entries.
        diagnostics: Diagnostic records emitted by the interface checker.
    """

    includes_interfaces = any(
        record.tool == PYQA_INTERFACES_TOOL or record.code == PYQA_INTERFACES_CODE for record in diagnostics
    )
    if not includes_interfaces:
        return
    accumulator.add(
        AdviceCategory.INTERFACE,
        (
            "Keep interfaces packages limited to Protocols, TypedDicts, dataclasses, and typed literals;"
            " move concrete helpers (functions, managers, service factories) into their runtime modules"
            " and depend on them via DI to maintain SOLID boundaries."
        ),
    )


def _append_interface_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Highlight undefined interfaces reported by type checkers.

    Args:
        accumulator: Collector receiving interface hygiene advice.
        diagnostics: Diagnostic records signalling missing or undefined members.
    """

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


def _append_python_hygiene_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Encourage structured logging and orchestrated exits for hygiene findings.

    Args:
        accumulator: Collector receiving hygiene advice entries.
        diagnostics: Diagnostic records produced by python-hygiene tooling.
    """

    if not diagnostics:
        return
    has_print = False
    has_exit = False
    for record in diagnostics:
        code = (record.code or "").upper()
        if record.tool in PYTHON_HYGIENE_TOOLS:
            if code.endswith("PRINT"):
                has_print = True
            if code.endswith("SYSTEM-EXIT"):
                has_exit = True
    if has_print:
        accumulator.add(
            AdviceCategory.LOGGING,
            (
                "Route user-facing output through structured logging helpers such as"
                " `pyqa.core.logging.public` or the CLI logger instead of raw print/pprint so"
                " reporters stay consistent and colour-aware."
            ),
        )
    if has_exit:
        accumulator.add(
            AdviceCategory.RUNTIME_SAFETY,
            (
                "Replace direct `SystemExit`/`os._exit` calls with orchestrator exit helpers or command"
                " results so the pipeline can persist diagnostics and teardown safely."
            ),
        )


def _append_focus_guidance(
    accumulator: _AdviceAccumulator,
    diagnostics: Sequence[DiagnosticRecord],
) -> None:
    """Identify high-density diagnostic files to direct focus.

    Args:
        accumulator: Collector receiving prioritisation advice entries.
        diagnostics: Diagnostic records generated during the run.
    """

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
    """Return ``True`` when ``path`` belongs to a test directory.

    Args:
        path: File system path to evaluate.

    Returns:
        bool: ``True`` when the path appears to reference a test-related file.
    """

    if not path:
        return False
    try:
        normalised = normalize_path(path)
    except (ValueError, OSError):
        normalised = Path(path)
    parts = [part.lower() for part in normalised.parts]
    return any(part.startswith("test") or part in TEST_TOKENS for part in parts)


@memoize(maxsize=1)
def _duplicate_hint_code_map() -> dict[str, set[str]]:
    """Return catalog-backed duplicate hint codes with fallback defaults.

    Returns:
        dict[str, set[str]]: Mapping of tool identifiers to diagnostic codes that
        indicate duplicate findings.

    """
    catalog_codes = catalog_duplicate_hint_codes()
    return {tool.lower(): {code.upper() for code in codes} for tool, codes in catalog_codes.items()}


def _summarise_paths(paths: Sequence[str], *, limit: int = 5) -> str:
    """Return a human-readable summary of the provided paths.

    Args:
        paths: Ordered collection of file system paths to summarise.
        limit: Maximum number of paths to include explicitly.

    Returns:
        str: Comma separated summary string suitable for advice copy.
    """

    if not paths:
        return ""
    shown = list(paths[:limit])
    summary = ", ".join(shown)
    remainder = len(paths) - len(shown)
    if remainder > 0:
        summary = f"{summary}, ... (+{remainder} more)"
    return summary


ANNOTATION_SPAN_STYLE: Final[str] = "ansi256:213"
ANNOTATION_ARGUMENT_TOKEN: Final[str] = "argument"


def _infer_annotation_targets(message: str, engine: AnnotationProvider) -> int:
    """Return the number of highlighted annotation spans within *message*.

    Args:
        message: Diagnostic message generated by the linter.
        engine: Annotation provider capable of highlighting spans.

    Returns:
        int: Estimated number of targets requiring annotations.
    """

    spans = engine.message_spans(message)
    highlighted = sum(1 for span in spans if span.style == ANNOTATION_SPAN_STYLE)
    if highlighted:
        return highlighted
    if ANNOTATION_ARGUMENT_TOKEN in message:
        tail = message.split(ANNOTATION_ARGUMENT_TOKEN, 1)[1]
        candidates = [token.strip(" `.,") for token in tail.split(",") if token.strip(" `.,")]
        return len(candidates)
    return 0


__all__ = [
    "AdviceBuilder",
    "AdviceEntry",
    "generate_advice",
]


def _create_default_annotation_provider() -> AnnotationProvider:
    """Return the default annotation provider implementation.

    Returns:
        AnnotationProvider: Default annotation provider used for advice generation.
    """
    return NullAnnotationProvider()
