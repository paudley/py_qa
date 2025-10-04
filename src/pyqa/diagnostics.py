# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Diagnostic normalization and deduplication helpers."""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Final

from .annotations import AnnotationEngine
from .config import DedupeConfig
from .models import Diagnostic, RawDiagnostic, RunResult
from .severity import (
    DEFAULT_SEVERITY_RULES,
    Severity,
    SeverityRuleMap,
    SeverityRuleView,
    add_custom_rule,
    apply_severity_rules,
)

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

_ANNOTATION_ENGINE = AnnotationEngine()


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
    """Return severity rules including any custom overrides."""
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
    """Normalize diagnostics into the canonical :class:`Diagnostic` form."""
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
    diagnostic: Diagnostic
    outcome_index: int


def dedupe_outcomes(result: RunResult, cfg: DedupeConfig) -> None:
    """Mutate ``result`` so that diagnostics are deduplicated according to *cfg*."""
    if not cfg.dedupe:
        return

    _ANNOTATION_ENGINE.annotate_run(result)

    kept: list[_DedupEntry] = []
    for outcome_index, outcome in enumerate(result.outcomes):
        deduped: list[Diagnostic] = []
        for diag in outcome.diagnostics:
            replacement = False
            for entry in kept:
                if not _is_duplicate(entry.diagnostic, diag, cfg):
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


def _is_duplicate(existing: Diagnostic, candidate: Diagnostic, cfg: DedupeConfig) -> bool:
    if not _within_same_scope(existing, candidate, cfg):
        return False

    if _codes_match(existing, candidate):
        return _messages_compatible(existing, candidate) and _lines_within_fuzz(
            existing,
            candidate,
            cfg.dedupe_line_fuzz,
        )

    if _cross_tool_equivalent(existing, candidate):
        return True

    return _semantic_overlap(existing, candidate)


def _line_distance(lhs: int | None, rhs: int | None) -> int:
    if lhs is None or rhs is None:
        return 0 if lhs == rhs else _DEFAULT_DISTANCE
    return abs(lhs - rhs)


def _prefer(existing: Diagnostic, candidate: Diagnostic, cfg: DedupeConfig) -> Diagnostic:
    pair = frozenset(code for code in (existing.code, candidate.code) if code)
    preferred_tool = _CODE_PREFERENCE.get(pair)
    if preferred_tool:
        if (existing.tool or "").lower() == preferred_tool:
            return existing
        if (candidate.tool or "").lower() == preferred_tool:
            return candidate
    strategy = cfg.dedupe_by or _STRATEGY_FIRST
    if strategy == _STRATEGY_FIRST:
        return existing
    if strategy == _STRATEGY_SEVERITY:
        return _higher_severity(existing, candidate)
    if strategy == _STRATEGY_PREFER:
        preferred = _prefer_list(existing, candidate, cfg.dedupe_prefer)
        return preferred if preferred is not None else _higher_severity(existing, candidate)
    return existing


def _semantic_overlap(left: Diagnostic, right: Diagnostic) -> bool:
    """Return ``True`` when diagnostics describe the same semantic issue."""
    if (left.file or "") != (right.file or ""):
        return False

    if left.function and right.function and left.function != right.function:
        return False

    tag_left = _issue_tag(left)
    if tag_left is None or tag_left != _issue_tag(right):
        return False

    signature_left = set(_ANNOTATION_ENGINE.message_signature(left.message))
    signature_right = set(_ANNOTATION_ENGINE.message_signature(right.message))
    signature_equal = _signatures_match(left, right, signature_left, signature_right)

    if tag_left is IssueTag.TYPING:
        return _typing_overlap(left, right, signature_left, signature_right)
    if tag_left is IssueTag.COMPLEXITY:
        return _complexity_overlap(signature_left, signature_right, signature_equal)
    return signature_equal


def _issue_tag(diag: Diagnostic) -> IssueTag | None:
    """Return the semantic category inferred from a diagnostic."""
    code = (diag.code or "").upper()
    signature = set(_ANNOTATION_ENGINE.message_signature(diag.message))

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
    return lhs if _severity_rank(lhs) >= _severity_rank(rhs) else rhs


def _severity_rank(diag: Diagnostic) -> int:
    return _SEVERITY_RANK.get(diag.severity, 0)


def _prefer_list(
    existing: Diagnostic,
    candidate: Diagnostic,
    prefer: Sequence[str],
) -> Diagnostic | None:
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
]


def _within_same_scope(existing: Diagnostic, candidate: Diagnostic, cfg: DedupeConfig) -> bool:
    """Return ``True`` when diagnostics belong to the same logical scope."""
    if cfg.dedupe_same_file_only:
        if existing.file != candidate.file:
            return False
        if existing.file is None and candidate.file is not None:
            return False
    if (existing.function or "") != (candidate.function or ""):
        return False
    return True


def _codes_match(existing: Diagnostic, candidate: Diagnostic) -> bool:
    """Return ``True`` when diagnostic codes are equivalent."""
    return _normalized_code(existing) == _normalized_code(candidate)


def _messages_compatible(existing: Diagnostic, candidate: Diagnostic) -> bool:
    """Return ``True`` when diagnostic messages reference the same issue."""
    if existing.message == candidate.message:
        return True
    return _semantic_overlap(existing, candidate)


def _cross_tool_equivalent(existing: Diagnostic, candidate: Diagnostic) -> bool:
    """Return ``True`` when cross-tool equivalence maps the diagnostics."""
    if existing.function != candidate.function or existing.line != candidate.line:
        return False
    codes = {code for code in (_normalized_code(existing), _normalized_code(candidate)) if code}
    return bool(codes) and frozenset(codes) in _CROSS_TOOL_EQUIVALENT_CODES


def _lines_within_fuzz(existing: Diagnostic, candidate: Diagnostic, fuzz: int) -> bool:
    """Return ``True`` when diagnostics appear within the configured fuzz range."""
    return _line_distance(existing.line, candidate.line) <= fuzz


def _signatures_match(
    left: Diagnostic,
    right: Diagnostic,
    left_signature: set[str],
    right_signature: set[str],
) -> bool:
    """Return ``True`` when message signatures indicate the same content."""
    if left.code and right.code and left.code == right.code:
        return True
    return left_signature == right_signature


def _typing_overlap(
    left: Diagnostic,
    right: Diagnostic,
    left_signature: set[str],
    right_signature: set[str],
) -> bool:
    """Return ``True`` when typing diagnostics describe the same symbol."""
    if left.line != right.line:
        return False
    return bool(left_signature & right_signature)


def _complexity_overlap(
    left_signature: set[str],
    right_signature: set[str],
    signature_equal: bool,
) -> bool:
    """Return ``True`` when complexity diagnostics target the same construct."""
    if signature_equal:
        return True
    common = {"complex", "complexity", "statement", "branch"}
    return bool(left_signature & right_signature & common)


def _normalized_code(diag: Diagnostic) -> str:
    """Return a normalized diagnostic code for comparison purposes."""
    return (diag.code or "").lower()
