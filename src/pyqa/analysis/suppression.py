# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Generate suppression hints for diagnostics."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from ..annotations import AnnotationEngine, HighlightKind
from ..models import Diagnostic, RunResult


_TEST_PREFIXES = ("tests/", "test/")


def apply_suppression_hints(result: RunResult, engine: AnnotationEngine) -> None:
    """Populate ``diagnostic.hints`` with suppression guidance."""

    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            hints = list(diag.hints)
            hints.extend(_hints_for_diagnostic(diag, engine))
            if hints:
                diag.hints = tuple(dict.fromkeys(hints))


def _hints_for_diagnostic(diag: Diagnostic, engine: AnnotationEngine) -> Iterable[str]:
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
                "Add to `[testing] suppressions` or mark the specific test case with an inline ignore if this behaviour is intentional.",
            ),
        )

    if tool in {"ruff", "pylint"} and code:
        args = _extract_arguments(diag, engine)
        if args:
            formatted_args = ", ".join(f"`{name}`" for name in args)
            arg_phrase = f" for argument(s) {formatted_args}"
        else:
            arg_phrase = ""
        hints.append(
            _format_hint(
                diag,
                f"{tool}.{code}",
                f"Inline suppression via `# noqa: {code}` or `# pylint: disable={code.lower()}`{arg_phrase}.",
            ),
        )

    if tool in {"mypy", "pyright"} and "annotation" in diag.message.lower():
        hints.append(
            _format_hint(
                diag,
                f"{tool}.{code}",
                "Use `# type: ignore[{code}]` on the specific assignment or add a stub entry if the upstream library is missing typings.".format(
                    code=code.lower(),
                ),
            ),
        )

    return hints


def _format_hint(diag: Diagnostic, suppression_key: str, guidance: str) -> str:
    function = diag.function or "this scope"
    return (
        f"Suppression candidate ({suppression_key}) in {function}: {guidance}"
    )


def _extract_arguments(diag: Diagnostic, engine: AnnotationEngine) -> list[str]:
    spans = engine.message_spans(diag.message)
    args: list[str] = []
    for span in spans:
        if span.kind == "argument":
            args.append(diag.message[span.start : span.end])
    return list(dict.fromkeys(args))


__all__ = ["apply_suppression_hints"]
