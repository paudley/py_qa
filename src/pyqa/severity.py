# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Severity related types and helpers."""

from __future__ import annotations

import re
from enum import Enum
from typing import Final, Iterable, Mapping, MutableMapping, cast


class Severity(str, Enum):
    """Severity levels normalising different tool vocabularies."""

    ERROR = "error"
    WARNING = "warning"
    NOTICE = "notice"
    NOTE = "note"


SeverityRule = tuple[re.Pattern[str], Severity]
SeverityRuleMap = MutableMapping[str, list[SeverityRule]]
SeverityRuleView = Mapping[str, Iterable[SeverityRule]]


DEFAULT_SEVERITY_RULES: Final[dict[str, list[SeverityRule]]] = {
    "ruff": [(re.compile(r"^(D|N)\d{3,4}"), Severity.NOTICE)],
    "pylint": [
        (re.compile(r"^C\d{4}"), Severity.NOTICE),
        (re.compile(r"^R\d{4}"), Severity.NOTICE),
    ],
}


def apply_severity_rules(
    tool: str,
    code_or_message: str,
    severity: Severity,
    *,
    rules: SeverityRuleView | None = None,
) -> Severity:
    """Apply tool-specific overrides to a diagnostic severity."""

    active_rules: SeverityRuleView = (
        rules if rules is not None else DEFAULT_SEVERITY_RULES
    )
    candidates = active_rules.get(tool, cast(Iterable[SeverityRule], ()))
    for pattern, sev in candidates:
        if pattern.search(code_or_message or ""):
            return Severity(sev)
    return severity


def add_custom_rule(
    spec: str,
    *,
    rules: SeverityRuleMap | None = None,
) -> str | None:
    """Add a custom severity override defined as ``tool:regex=level``."""

    target: SeverityRuleMap = rules if rules is not None else DEFAULT_SEVERITY_RULES
    try:
        tool, rest = spec.split(":", 1)
        regex, level_str = rest.rsplit("=", 1)
        level = Severity(level_str.strip().lower())
    except ValueError as exc:  # covers ValueError from split or enum conversion
        return f"invalid rule '{spec}': {exc}"

    target.setdefault(tool, []).append((re.compile(regex), level))
    return None


def severity_from_code(
    code: str | None, default: Severity = Severity.ERROR
) -> Severity:
    """Infer severity from conventional code prefixes (e.g. E, W)."""

    if not code:
        return default
    head = code[0].upper()
    if head in {"E", "F"}:
        return Severity.ERROR
    if head == "W":
        return Severity.WARNING
    return default


_SEVERITY_TO_SARIF_LEVEL: Final[dict[Severity, str]] = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.NOTICE: "note",
    Severity.NOTE: "note",
}


def severity_to_sarif(severity: Severity) -> str:
    """Map :class:`Severity` to a SARIF reporting level."""

    return _SEVERITY_TO_SARIF_LEVEL.get(severity, "warning")
