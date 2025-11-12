# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Severity related types and helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, MutableMapping
from enum import Enum
from typing import Final, cast


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
    """Apply tool-specific overrides to a diagnostic severity.

    Args:
        tool: Tool identifier associated with the diagnostic.
        code_or_message: Diagnostic code or message text used when matching rules.
        severity: Baseline severity reported by the tool.
        rules: Optional overrides mapping per-tool regex patterns to severities.

    Returns:
        Severity: Overridden severity when a rule matches, otherwise the original severity.
    """
    active_rules: SeverityRuleView = rules if rules is not None else DEFAULT_SEVERITY_RULES
    candidates = active_rules.get(tool, cast("Iterable[SeverityRule]", ()))
    for pattern, sev in candidates:
        if pattern.search(code_or_message or ""):
            return Severity(sev)
    return severity


def add_custom_rule(
    spec: str,
    *,
    rules: SeverityRuleMap | None = None,
) -> str | None:
    """Add a custom severity override defined as ``tool:regex=level``.

    Args:
        spec: Rule specification using ``tool:regex=severity`` format.
        rules: Override mapping to update; defaults to :data:`DEFAULT_SEVERITY_RULES`.

    Returns:
        str | None: Error message when parsing fails, otherwise ``None``.
    """
    target: SeverityRuleMap = rules if rules is not None else DEFAULT_SEVERITY_RULES
    if _RULE_TOOL_SEPARATOR not in spec or _RULE_LEVEL_SEPARATOR not in spec:
        return f"invalid rule '{spec}': missing ':' or '=' separators"
    tool, rest = spec.split(_RULE_TOOL_SEPARATOR, 1)
    regex, level_str = rest.rsplit(_RULE_LEVEL_SEPARATOR, 1)
    try:
        level = Severity(level_str.strip().lower())
    except ValueError as exc:
        return f"invalid severity level '{level_str}': {exc}"

    target.setdefault(tool, []).append((re.compile(regex), level))
    return None


def severity_from_code(code: str | None, default: Severity = Severity.ERROR) -> Severity:
    """Infer severity from conventional code prefixes (e.g. E, W).

    Args:
        code: Diagnostic code emitted by the tool.
        default: Severity returned when the code does not match known prefixes.

    Returns:
        Severity: Severity derived from the code or ``default`` when unmatched.
    """
    if not code:
        return default
    head = code[0].upper()
    if head in _ERROR_PREFIXES:
        return Severity.ERROR
    if head == _WARNING_PREFIX:
        return Severity.WARNING
    return default


_SEVERITY_TO_SARIF_LEVEL: Final[dict[Severity, str]] = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.NOTICE: "note",
    Severity.NOTE: "note",
}


def severity_to_sarif(severity: Severity) -> str:
    """Map :class:`Severity` to a SARIF reporting level.

    Args:
        severity: Severity value to translate.

    Returns:
        str: SARIF level string compatible with SARIF output.
    """
    return _SEVERITY_TO_SARIF_LEVEL.get(severity, "warning")


_ERROR_PREFIXES: Final[set[str]] = {"E", "F"}
_WARNING_PREFIX: Final[str] = "W"
_RULE_TOOL_SEPARATOR: Final[str] = ":"
_RULE_LEVEL_SEPARATOR: Final[str] = "="
