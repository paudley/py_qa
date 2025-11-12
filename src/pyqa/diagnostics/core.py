# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Diagnostic normalization and deduplication helpers."""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Final

from pyqa.core.severity import (
    DEFAULT_SEVERITY_RULES,
    Severity,
    SeverityRuleMap,
    SeverityRuleView,
    add_custom_rule,
    apply_severity_rules,
)

from ..analysis.providers import NullAnnotationProvider
from ..config import DedupeConfig
from ..core.models import Diagnostic, RawDiagnostic, RunResult
from ..interfaces.analysis import AnnotationProvider

_SEVERITY_RANK: MutableMapping[Severity, int] = {
    Severity.ERROR: 3,
    Severity.WARNING: 2,
    Severity.NOTICE: 1,
    Severity.NOTE: 0,
}

_CROSS_TOOL_EQUIVALENT_CODES: Final[set[frozenset[str]]] = {
    frozenset({"override", "w0221"}),
    frozenset({"tc002", "reportprivateimportusage"}),
    frozenset({"f822", "reportunsupporteddunderall"}),
    frozenset({"f821", "reportundefinedvariable"}),
    frozenset({"f821", "undefined-variable"}),
    frozenset({"plr2004", "r2004"}),
    frozenset({"undefined-variable", "reportundefinedvariable"}),
    frozenset({"arg-type", "reportargumenttype"}),
}

_CODE_PREFERENCE: Final[dict[frozenset[str], str]] = {
    frozenset({"arg-type", "reportArgumentType"}): "pyright",
}


class IssueTag(str, Enum):
    """Enumerate semantic categories recognised during deduplication."""

    COMPLEXITY = "complexity"
    MAGIC_NUMBER = "magic-number"
    TYPING = "typing"
    DOCSTRING = "docstring"
    ENCAPSULATION = "encapsulation"


_COMPLEXITY_SIGNATURE_TOKENS: Final[frozenset[str]] = frozenset({"complex", "complexity"})
_MAGIC_SIGNATURE_TOKENS: Final[frozenset[str]] = frozenset({"magic"})
_DOCSTRING_SIGNATURE_TOKENS: Final[frozenset[str]] = frozenset({"docstring"})
_ENCAPSULATION_TOKENS: Final[frozenset[str]] = frozenset({"private", "import"})
_TYPING_SIGNATURE_TOKENS: Final[frozenset[str]] = frozenset({"annotation", "typed"})
_COMPLEXITY_CODES: Final[frozenset[str]] = frozenset({"C901", "R0915", "PLR0915", "R1260"})
_MAGIC_NUMBER_CODES: Final[frozenset[str]] = frozenset({"PLR2004", "R2004"})
_DOCSTRING_CODE_PREFIX: Final[str] = "D1"
_ANNOTATION_PREFIX: Final[str] = "ANN"
_DEFAULT_DISTANCE: Final[int] = 10**6
_STRATEGY_FIRST: Final[str] = "first"
_STRATEGY_SEVERITY: Final[str] = "severity"
_STRATEGY_PREFER: Final[str] = "prefer"


def build_severity_rules(custom_rules: Iterable[str]) -> SeverityRuleMap:
    """Return severity rules including the supplied custom overrides.

    Args:
        custom_rules: Rule strings that should augment the default map.

    Returns:
        SeverityRuleMap: Normalised map containing both default and custom rules.
    """
    rules = deepcopy(DEFAULT_SEVERITY_RULES)
    for rule in custom_rules:
        add_custom_rule(rule, rules=rules)
    return rules


def normalize_diagnostics(
    candidates: Sequence[RawDiagnostic | Diagnostic],
    *,
    tool_name: str,
    severity_rules: SeverityRuleView,
) -> list[Diagnostic]:
    """Normalize heterogeneous diagnostic payloads into canonical models.

    Args:
        candidates: Raw or already normalised diagnostics emitted by a tool.
        tool_name: Name of the tool responsible for ``candidates``.
        severity_rules: Active severity rules applied during normalisation.

    Returns:
        list[Diagnostic]: Diagnostics coerced into the canonical representation.
    """
    normalized: list[Diagnostic] = []
    for candidate in candidates:
        if isinstance(candidate, Diagnostic):
            normalized.append(candidate)
            continue
        normalized.append(_normalize_raw(candidate, tool_name, severity_rules))
    return normalized


def _normalize_raw(
    raw: RawDiagnostic,
    tool_name: str,
    severity_rules: SeverityRuleView,
) -> Diagnostic:
    """Convert ``raw`` diagnostics into their canonical representation.

    Args:
        raw: Raw diagnostic payload produced by a tool integration.
        tool_name: Tool name used when the diagnostic omits the field.
        severity_rules: Severity rule map used to calibrate severity values.

    Returns:
        Diagnostic: Canonical diagnostic populated with coerced values.
    """
    message = raw.message.strip()
    code = raw.code
    tool = raw.tool or tool_name
    severity = _coerce_severity(raw.severity)

    if code:
        trimmed = message.lstrip()
        for prefix in (
            f"{code}:",
            f"{code} -",
            f"{code},",
            f"{code} ",
            f"[{code}]",
            f"({code})",
        ):
            if trimmed.startswith(prefix):
                trimmed = trimmed[len(prefix) :].lstrip()
                break
        message = trimmed or message
        if not message.startswith(code):
            message = f"{code} {message}".strip()

    severity = apply_severity_rules(tool, code or message, severity, rules=severity_rules)

    return Diagnostic(
        file=raw.file,
        line=raw.line,
        column=raw.column,
        severity=severity,
        message=message,
        tool=tool,
        code=code,
        group=raw.group,
        function=raw.function,
    )


def _coerce_severity(value: Severity | str | None) -> Severity:
    """Return a :class:`Severity` enumeration value for ``value``.

    Args:
        value: Raw severity entry which may already be an enum, string, or ``None``.

    Returns:
        Severity: Coerced severity value defaulting to ``Severity.WARNING`` on error.
    """
    if isinstance(value, Severity):
        return value
    if isinstance(value, str):
        try:
            return Severity(value.lower())
        except ValueError:
            return Severity.WARNING
    return Severity.WARNING


@dataclass
class _DedupEntry:
    """Track a diagnostic along with the originating outcome index."""

    diagnostic: Diagnostic
    outcome_index: int


def dedupe_outcomes(
    result: RunResult,
    cfg: DedupeConfig,
    *,
    annotation_provider: AnnotationProvider | None = None,
) -> None:
    """Deduplicate diagnostics found in ``result`` according to ``cfg``.

    Args:
        result: Run result containing outcome diagnostics that may overlap.
        cfg: Deduplication configuration describing scope and preference rules.
        annotation_provider: Optional annotation provider used to enrich
            diagnostics before semantic comparison. When omitted, the default
            provider registered in the analysis service container is resolved.
    """
    if not cfg.dedupe:
        return

    engine = annotation_provider or NullAnnotationProvider()
    engine.annotate_run(result)

    kept: list[_DedupEntry] = []
    for outcome_index, outcome in enumerate(result.outcomes):
        deduped: list[Diagnostic] = []
        for diag in outcome.diagnostics:
            replacement = False
            for entry in kept:
                if not _is_duplicate(entry.diagnostic, diag, cfg, engine):
                    continue
                preferred = _prefer(entry.diagnostic, diag, cfg)
                if preferred is entry.diagnostic:
                    replacement = True
                    break
                entry.diagnostic = preferred
                entry.outcome_index = outcome_index
                replacement = True
                break
            if not replacement:
                kept.append(_DedupEntry(diag, outcome_index))
                deduped.append(diag)
        outcome.diagnostics = deduped

    # Rebuild outcome diagnostics to reflect any replacements.
    for outcome in result.outcomes:
        outcome.diagnostics = []
    for entry in kept:
        result.outcomes[entry.outcome_index].diagnostics.append(entry.diagnostic)


def _is_duplicate(
    existing: Diagnostic,
    candidate: Diagnostic,
    cfg: DedupeConfig,
    engine: AnnotationProvider,
) -> bool:
    """Return ``True`` when ``candidate`` duplicates ``existing`` under ``cfg``.

    Args:
        existing: Diagnostic already retained by the deduper.
        candidate: Newly observed diagnostic under evaluation.
        cfg: Deduplication configuration governing comparison behaviour.
        engine: Annotation provider used to derive semantic message signatures.

    Returns:
        bool: ``True`` when both diagnostics represent the same issue.
    """
    if not _within_same_scope(existing, candidate, cfg):
        return False

    if _codes_match(existing, candidate):
        return _messages_compatible(existing, candidate, engine) and _lines_within_fuzz(
            existing,
            candidate,
            cfg.dedupe_line_fuzz,
        )

    if _cross_tool_equivalent(existing, candidate):
        return True

    return _semantic_overlap(existing, candidate, engine)


def _line_distance(lhs: int | None, rhs: int | None) -> int:
    """Return the absolute difference between ``lhs`` and ``rhs`` line numbers.

    Args:
        lhs: First line number or ``None`` when unspecified.
        rhs: Second line number or ``None`` when unspecified.

    Returns:
        int: Absolute line distance or a large sentinel when either entry is ``None``.
    """
    if lhs is None or rhs is None:
        return 0 if lhs == rhs else _DEFAULT_DISTANCE
    return abs(lhs - rhs)


def _prefer(existing: Diagnostic, candidate: Diagnostic, cfg: DedupeConfig) -> Diagnostic:
    """Return the diagnostic preferred by the configuration heuristics.

    Args:
        existing: Diagnostic retained so far.
        candidate: Diagnostic competing with ``existing``.
        cfg: Deduplication configuration capturing the preference strategy.

    Returns:
        Diagnostic: Preferred diagnostic based on tool, severity, or ordering rules.
    """
    pair = frozenset(code for code in (existing.code, candidate.code) if code)
    preferred_tool = _CODE_PREFERENCE.get(pair)
    if preferred_tool:
        if (existing.tool or "").lower() == preferred_tool:
            return existing
        if (candidate.tool or "").lower() == preferred_tool:
            return candidate
    strategy = cfg.dedupe_by
    if strategy == _STRATEGY_FIRST:
        return existing
    if strategy == _STRATEGY_SEVERITY:
        return _higher_severity(existing, candidate)
    if strategy == _STRATEGY_PREFER:
        preferred = _prefer_list(existing, candidate, cfg.dedupe_prefer)
        return preferred if preferred is not None else _higher_severity(existing, candidate)
    raise ValueError(f"Unknown deduplication strategy: {strategy!r}")


def _semantic_overlap(
    left: Diagnostic,
    right: Diagnostic,
    engine: AnnotationProvider,
) -> bool:
    """Return ``True`` when diagnostics describe the same semantic issue.

    Args:
        left: First diagnostic candidate.
        right: Second diagnostic candidate.
        engine: Annotation provider used to derive semantic signatures.

    Returns:
        bool: ``True`` when diagnostics align semantically.
    """
    if (left.file or "") != (right.file or ""):
        return False

    if left.function and right.function and left.function != right.function:
        return False

    tag_left = _issue_tag(left, engine)
    if tag_left is None or tag_left != _issue_tag(right, engine):
        return False

    signature_left = set(engine.message_signature(left.message))
    signature_right = set(engine.message_signature(right.message))
    signature_equal = _signatures_match(left, right, signature_left, signature_right)

    if tag_left is IssueTag.TYPING:
        return _typing_overlap(left, right, signature_left, signature_right)
    if tag_left is IssueTag.COMPLEXITY:
        return _complexity_overlap(signature_left, signature_right, signature_equal)
    return signature_equal


def _issue_tag(diag: Diagnostic, engine: AnnotationProvider) -> IssueTag | None:
    """Return the semantic category inferred from a diagnostic.

    Args:
        diag: Diagnostic whose message signatures should be classified.
        engine: Annotation provider used to extract signature tokens.

    Returns:
        IssueTag | None: Category describing the diagnostic or ``None`` when unknown.
    """
    code = (diag.code or "").upper()
    signature = set(engine.message_signature(diag.message))

    if code in _COMPLEXITY_CODES or signature & _COMPLEXITY_SIGNATURE_TOKENS:
        return IssueTag.COMPLEXITY
    if code in _MAGIC_NUMBER_CODES or signature & _MAGIC_SIGNATURE_TOKENS:
        return IssueTag.MAGIC_NUMBER
    if code.startswith(_ANNOTATION_PREFIX) or signature & _TYPING_SIGNATURE_TOKENS:
        return IssueTag.TYPING
    if code.startswith(_DOCSTRING_CODE_PREFIX) or signature & _DOCSTRING_SIGNATURE_TOKENS:
        return IssueTag.DOCSTRING
    if signature.issuperset(_ENCAPSULATION_TOKENS):
        return IssueTag.ENCAPSULATION
    return None


def _higher_severity(lhs: Diagnostic, rhs: Diagnostic) -> Diagnostic:
    """Return the diagnostic with the higher severity ranking.

    Args:
        lhs: First diagnostic candidate.
        rhs: Second diagnostic candidate.

    Returns:
        Diagnostic: Diagnostic with the highest severity according to rank mapping.
    """
    return lhs if _severity_rank(lhs) >= _severity_rank(rhs) else rhs


def _severity_rank(diag: Diagnostic) -> int:
    """Return the numeric rank associated with ``diag`` severity.

    Args:
        diag: Diagnostic whose severity rank is required.

    Returns:
        int: Severity rank where higher numbers represent more severe diagnostics.
    """

    return _SEVERITY_RANK.get(diag.severity, 0)


def _prefer_list(
    existing: Diagnostic,
    candidate: Diagnostic,
    prefer: Sequence[str],
) -> Diagnostic | None:
    """Select a preferred diagnostic based on tool ordering.

    Args:
        existing: Diagnostic retained so far.
        candidate: Diagnostic being evaluated.
        prefer: Ordered tool preference list.

    Returns:
        Diagnostic | None: Preferred diagnostic when the list resolves a tie, otherwise ``None``.
    """
    if not prefer:
        return None
    try:
        existing_index = prefer.index(existing.tool)
    except ValueError:
        existing_index = len(prefer)
    try:
        candidate_index = prefer.index(candidate.tool)
    except ValueError:
        candidate_index = len(prefer)

    if existing_index == candidate_index:
        return None
    return existing if existing_index < candidate_index else candidate


__all__ = [
    "build_severity_rules",
    "dedupe_outcomes",
    "normalize_diagnostics",
    "IssueTag",
]


def _within_same_scope(existing: Diagnostic, candidate: Diagnostic, cfg: DedupeConfig) -> bool:
    """Return ``True`` when diagnostics belong to the same logical scope.

    Args:
        existing: Diagnostic already retained by the deduper.
        candidate: Diagnostic currently under evaluation.
        cfg: Deduplication configuration describing scope constraints.

    Returns:
        bool: ``True`` when diagnostics share file/function scope as required.
    """
    if cfg.dedupe_same_file_only:
        if existing.file != candidate.file:
            return False
        if existing.file is None and candidate.file is not None:
            return False
    if (existing.function or "") != (candidate.function or ""):
        return False
    return True


def _codes_match(existing: Diagnostic, candidate: Diagnostic) -> bool:
    """Return ``True`` when diagnostic codes are equivalent.

    Args:
        existing: Reference diagnostic that has already been retained.
        candidate: Diagnostic being evaluated for duplication.

    Returns:
        bool: ``True`` when codes normalise to the same token.
    """
    return _normalized_code(existing) == _normalized_code(candidate)


def _messages_compatible(
    existing: Diagnostic,
    candidate: Diagnostic,
    engine: AnnotationProvider,
) -> bool:
    """Return ``True`` when diagnostic messages reference the same issue.

    Args:
        existing: Diagnostic already retained.
        candidate: Diagnostic being evaluated.
        engine: Annotation provider used to extract semantic signatures.

    Returns:
        bool: ``True`` when both diagnostics describe the same situation.
    """
    if existing.message == candidate.message:
        return True
    return _semantic_overlap(existing, candidate, engine)


def _cross_tool_equivalent(existing: Diagnostic, candidate: Diagnostic) -> bool:
    """Return ``True`` when cross-tool equivalence maps the diagnostics.

    Args:
        existing: Diagnostic already retained.
        candidate: Diagnostic being evaluated.

    Returns:
        bool: ``True`` when configured code equivalence declares both identical.
    """
    if existing.function != candidate.function or existing.line != candidate.line:
        return False
    codes = {code for code in (_normalized_code(existing), _normalized_code(candidate)) if code}
    return bool(codes) and frozenset(codes) in _CROSS_TOOL_EQUIVALENT_CODES


def _lines_within_fuzz(existing: Diagnostic, candidate: Diagnostic, fuzz: int) -> bool:
    """Return ``True`` when diagnostics appear within the configured fuzz range.

    Args:
        existing: Diagnostic already retained.
        candidate: Diagnostic being evaluated.
        fuzz: Maximum permissible line distance for duplicates.

    Returns:
        bool: ``True`` when diagnostics appear within the permitted fuzz distance.
    """
    return _line_distance(existing.line, candidate.line) <= fuzz


def _signatures_match(
    left: Diagnostic,
    right: Diagnostic,
    left_signature: set[str],
    right_signature: set[str],
) -> bool:
    """Return ``True`` when message signatures indicate the same content.

    Args:
        left: First diagnostic under comparison.
        right: Second diagnostic under comparison.
        left_signature: Tokenised signature for ``left``.
        right_signature: Tokenised signature for ``right``.

    Returns:
        bool: ``True`` when signature comparison confirms identical messages.
    """
    if left.code and right.code and left.code == right.code:
        return True
    return left_signature == right_signature


def _typing_overlap(
    left: Diagnostic,
    right: Diagnostic,
    left_signature: set[str],
    right_signature: set[str],
) -> bool:
    """Return ``True`` when typing diagnostics describe the same symbol.

    Args:
        left: First typing diagnostic to compare.
        right: Second typing diagnostic to compare.
        left_signature: Signature tokens extracted from ``left``.
        right_signature: Signature tokens extracted from ``right``.

    Returns:
        bool: ``True`` when signatures overlap for the same symbol and line.
    """
    if left.line != right.line:
        return False
    return bool(left_signature & right_signature)


def _complexity_overlap(
    left_signature: set[str],
    right_signature: set[str],
    signature_equal: bool,
) -> bool:
    """Return ``True`` when complexity diagnostics target the same construct.

    Args:
        left_signature: Signature tokens from the first diagnostic.
        right_signature: Signature tokens from the second diagnostic.
        signature_equal: ``True`` when signatures already match exactly.

    Returns:
        bool: ``True`` when complexity-focused diagnostics overlap.
    """
    if signature_equal:
        return True
    common = {"complex", "complexity", "statement", "branch"}
    return bool(left_signature & right_signature & common)


def _normalized_code(diag: Diagnostic) -> str:
    """Return a normalized diagnostic code for comparison purposes.

    Args:
        diag: Diagnostic whose code should be normalised.

    Returns:
        str: Lowercase diagnostic code suitable for equality comparisons.
    """
    return (diag.code or "").lower()
