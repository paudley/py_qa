# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Diagnostic normalization and deduplication helpers."""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from .annotations import AnnotationEngine
from .config import DedupeConfig
from .models import Diagnostic, RawDiagnostic, RunResult
from .path_utils import normalize_reported_path
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

_CROSS_TOOL_EQUIVALENT_CODES = {
    frozenset({"override", "W0221"}),
    frozenset({"TC002", "reportPrivateImportUsage"}),
    frozenset({"F822", "reportUnsupportedDunderAll"}),
    frozenset({"F821", "reportUndefinedVariable"}),
    frozenset({"PLR2004", "R2004"}),
}

_ANNOTATION_ENGINE = AnnotationEngine()


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
    root: Path | None = None,
) -> list[Diagnostic]:
    """Normalize diagnostics into the canonical :class:`Diagnostic` form."""
    normalized: list[Diagnostic] = []
    for candidate in candidates:
        if isinstance(candidate, Diagnostic):
            normalized.append(_normalize_existing(candidate, root=root))
            continue
        normalized.append(
            _normalize_raw(candidate, tool_name, severity_rules, root=root),
        )
    return normalized


def _normalize_raw(
    raw: RawDiagnostic,
    tool_name: str,
    severity_rules: SeverityRuleView,
    *,
    root: Path | None,
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
        file=_normalize_file_path(raw.file, root=root),
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


def _normalize_existing(diagnostic: Diagnostic, *, root: Path | None) -> Diagnostic:
    normalized_path = _normalize_file_path(diagnostic.file, root=root)
    if normalized_path == diagnostic.file:
        return diagnostic
    return diagnostic.model_copy(update={"file": normalized_path})


def _normalize_file_path(file_path: str | None, *, root: Path | None) -> str | None:
    return normalize_reported_path(file_path, root=root)


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
    if cfg.dedupe_same_file_only and existing.file != candidate.file:
        return False

    existing_code = existing.code or ""
    candidate_code = candidate.code or ""
    if existing_code != candidate_code:
        if existing.function == candidate.function and existing.line == candidate.line:
            pair = frozenset(code for code in (existing_code, candidate_code) if code)
            if pair in _CROSS_TOOL_EQUIVALENT_CODES:
                return True
        semantic_match = _semantic_overlap(existing, candidate)
        if semantic_match:
            return True
        return False

    if existing.message != candidate.message:
        semantic_match = _semantic_overlap(existing, candidate)
        if not semantic_match:
            return False

    if cfg.dedupe_same_file_only and existing.file is None and candidate.file is not None:
        return False

    if (existing.function or "") != (candidate.function or ""):
        return False

    if not cfg.dedupe_same_file_only and existing.file != candidate.file:
        # Allow dedupe across files when requested; rely on message/code equality
        pass

    return _line_distance(existing.line, candidate.line) <= cfg.dedupe_line_fuzz


def _line_distance(lhs: int | None, rhs: int | None) -> int:
    if lhs is None or rhs is None:
        return 0 if lhs == rhs else 10**6
    return abs(lhs - rhs)


def _prefer(existing: Diagnostic, candidate: Diagnostic, cfg: DedupeConfig) -> Diagnostic:
    if cfg.dedupe_by == "first":
        return existing
    if cfg.dedupe_by == "severity":
        return _higher_severity(existing, candidate)
    if cfg.dedupe_by == "prefer":
        preferred = _prefer_list(existing, candidate, cfg.dedupe_prefer)
        if preferred is not None:
            return preferred
        return _higher_severity(existing, candidate)
    return existing


def _semantic_overlap(left: Diagnostic, right: Diagnostic) -> bool:
    if (left.file or "") != (right.file or ""):
        return False

    if left.function and right.function and left.function != right.function:
        return False

    tag_left = _issue_tag(left)
    if not tag_left:
        return False
    tag_right = _issue_tag(right)
    if tag_left != tag_right:
        return False

    signature_left = set(_ANNOTATION_ENGINE.message_signature(left.message))
    signature_right = set(_ANNOTATION_ENGINE.message_signature(right.message))

    if left.code and right.code and left.code == right.code:
        signature_equal = True
    else:
        signature_equal = signature_left == signature_right

    if not signature_equal and tag_left not in {"complexity", "typing"}:
        return False

    if tag_left == "typing":
        if left.line != right.line:
            return False
        overlap = signature_left & signature_right
        if not overlap:
            return False

    if tag_left == "complexity" and not signature_equal:
        common = {"complex", "complexity", "statement", "branch"}
        if not (signature_left & signature_right & common):
            return False

    return True


def _issue_tag(diag: Diagnostic) -> str | None:
    code = (diag.code or "").upper()
    message = diag.message.lower()
    signature = set(_ANNOTATION_ENGINE.message_signature(diag.message))

    if (
        code in {"C901", "R0915", "PLR0915", "R1260"}
        or {
            "complex",
            "complexity",
        }
        & signature
    ):
        return "complexity"
    if code in {"PLR2004", "R2004"} or "magic" in signature:
        return "magic-number"
    if code.startswith("ANN") or "annotation" in signature or "typed" in signature:
        return "typing"
    if "docstring" in signature or code.startswith("D1"):
        return "docstring"
    if "private" in signature and "import" in signature:
        return "encapsulation"
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
