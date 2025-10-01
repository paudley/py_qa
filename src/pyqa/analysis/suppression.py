# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Generate suppression hints for diagnostics."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from ..annotations import AnnotationEngine
from ..models import Diagnostic, RunResult

_TEST_PREFIXES: Final[tuple[str, ...]] = ("tests/", "test/")
_INLINE_SUPPRESSION_TOOLS: Final[set[str]] = {"ruff", "pylint"}
_ANNOTATION_TOOLS: Final[set[str]] = {"mypy", "pyright"}
_ANNOTATION_KEYWORD: Final[str] = "annotation"
_GUIDANCE_TEST_SUPPRESSION: Final[str] = (
    "Add to `[testing] suppressions` or mark the specific test case with an inline ignore "
    "if this behaviour is intentional."
)
_RUFF_SUPPRESSION_TEMPLATE: Final[str] = "Inline suppression via `# noqa: {code}`"
_PYLINT_SUPPRESSION_TEMPLATE: Final[str] = "`# pylint: disable={code}`"
_TYPING_SUPPRESSION_TEMPLATE: Final[str] = (
    "Use `# type: ignore[{code}]` on the specific assignment or add a stub entry "
    "if the upstream library is missing typings."
)


def apply_suppression_hints(result: RunResult, engine: AnnotationEngine) -> None:
    """Populate ``diagnostic.hints`` with suppression guidance.

    Args:
        result: Aggregated run result whose diagnostics should receive hints.
        engine: Annotation engine used to interpret diagnostic messages.
    """

    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            hints = list(diag.hints)
            hints.extend(_hints_for_diagnostic(diag, engine))
            if hints:
                diag.hints = tuple(dict.fromkeys(hints))


def _hints_for_diagnostic(diag: Diagnostic, engine: AnnotationEngine) -> Iterable[str]:
    """Return suppression hints tailored to ``diag``.

    Args:
        diag: Diagnostic requiring optional suppression guidance.
        engine: Annotation engine used to extract structured message data.

    Returns:
        Iterable[str]: Iterable of formatted hint strings.
    """

    if not diag.code:
        return []

    code = diag.code.upper()
    tool = diag.tool.lower()
    file_path = (diag.file or "").replace("\\", "/")
    hints: list[str] = []

    if file_path.startswith(_TEST_PREFIXES):
        hints.append(
            _format_hint(
                diag,
                f"tests/{tool}.{code}",
                _GUIDANCE_TEST_SUPPRESSION,
            ),
        )

    if tool in _INLINE_SUPPRESSION_TOOLS:
        args = _extract_arguments(diag, engine)
        if args:
            formatted_args = ", ".join(f"`{name}`" for name in args)
            arg_phrase = f" for argument(s) {formatted_args}"
        else:
            arg_phrase = ""
        if tool == "ruff":
            detail = f"{_RUFF_SUPPRESSION_TEMPLATE.format(code=code)}{arg_phrase}."
        else:
            detail = f"{_PYLINT_SUPPRESSION_TEMPLATE.format(code=code.lower())}{arg_phrase}."
        hints.append(
            _format_hint(
                diag,
                f"{tool}.{code}",
                detail,
            ),
        )

    if tool in _ANNOTATION_TOOLS and _ANNOTATION_KEYWORD in diag.message.lower():
        hints.append(
            _format_hint(
                diag,
                f"{tool}.{code}",
                _TYPING_SUPPRESSION_TEMPLATE.format(code=code.lower()),
            ),
        )

    return hints


def _format_hint(diag: Diagnostic, suppression_key: str, guidance: str) -> str:
    """Return a formatted hint string for ``diag``.

    Args:
        diag: Diagnostic the hint refers to.
        suppression_key: Canonical configuration key for the suppression.
        guidance: Human readable suppression guidance text.

    Returns:
        str: Fully formatted hint entry.
    """

    function = diag.function or "this scope"
    return f"Suppression candidate ({suppression_key}) in {function}: {guidance}"


def _extract_arguments(diag: Diagnostic, engine: AnnotationEngine) -> list[str]:
    """Return argument identifiers highlighted in ``diag.message``.

    Args:
        diag: Diagnostic whose message spans should be inspected.
        engine: Annotation engine providing structured span metadata.

    Returns:
        list[str]: Unique argument names referenced by the diagnostic.
    """

    spans = engine.message_spans(diag.message)
    args: list[str] = []
    for span in spans:
        if span.kind == "argument":
            args.append(diag.message[span.start : span.end])
    return list(dict.fromkeys(args))


__all__ = ["apply_suppression_hints"]
