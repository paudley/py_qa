# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Generate suppression hints for diagnostics."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Final

from ..annotations import AnnotationEngine
from ..models import Diagnostic, RunResult

_TEST_PREFIXES: Final[tuple[str, ...]] = ("tests/", "test/")


class SuppressionTool(StrEnum):
    """Tools that support inline suppressions handled by pyqa."""

    RUFF = "ruff"
    PYLINT = "pylint"


class AnnotationTool(StrEnum):
    """Static analysis tools that emit annotation-related diagnostics."""

    MYPY = "mypy"
    PYRIGHT = "pyright"


class DiagnosticSpanKind(StrEnum):
    """Span kinds returned by :class:`AnnotationEngine`."""

    ARGUMENT = "argument"


_INLINE_SUPPRESSION_TOOLS: Final[set[SuppressionTool]] = {
    SuppressionTool.RUFF,
    SuppressionTool.PYLINT,
}
_ANNOTATION_TOOLS: Final[set[AnnotationTool]] = {
    AnnotationTool.MYPY,
    AnnotationTool.PYRIGHT,
}
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
    tool_name = diag.tool.lower()
    file_path = (diag.file or "").replace("\\", "/")
    hints: list[str] = []

    if file_path.startswith(_TEST_PREFIXES):
        hints.append(
            _format_hint(
                diag,
                f"tests/{tool_name}.{code}",
                _GUIDANCE_TEST_SUPPRESSION,
            ),
        )

    suppression_tool = _resolve_suppression_tool(tool_name)
    if suppression_tool is not None:
        args = _extract_arguments(diag, engine)
        if args:
            formatted_args = ", ".join(f"`{name}`" for name in args)
            arg_phrase = f" for argument(s) {formatted_args}"
        else:
            arg_phrase = ""
        if suppression_tool is SuppressionTool.RUFF:
            detail = f"{_RUFF_SUPPRESSION_TEMPLATE.format(code=code)}{arg_phrase}."
        else:
            detail = f"{_PYLINT_SUPPRESSION_TEMPLATE.format(code=code.lower())}{arg_phrase}."
        hints.append(
            _format_hint(
                diag,
                f"{suppression_tool.value}.{code}",
                detail,
            ),
        )

    annotation_tool = _resolve_annotation_tool(tool_name)
    if annotation_tool in _ANNOTATION_TOOLS and _ANNOTATION_KEYWORD in diag.message.lower():
        hints.append(
            _format_hint(
                diag,
                f"{annotation_tool.value}.{code}",
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
        if span.kind is not None and span.kind == DiagnosticSpanKind.ARGUMENT:
            args.append(diag.message[span.start : span.end])
    return list(dict.fromkeys(args))


def _resolve_suppression_tool(tool_name: str) -> SuppressionTool | None:
    """Return the suppression-aware tool enum for ``tool_name``."""

    try:
        candidate = SuppressionTool(tool_name)
    except ValueError:
        return None
    return candidate


def _resolve_annotation_tool(tool_name: str) -> AnnotationTool | None:
    """Return the annotation-aware tool enum for ``tool_name``."""

    try:
        candidate = AnnotationTool(tool_name)
    except ValueError:
        return None
    return candidate


__all__ = ["apply_suppression_hints"]
