# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Assemble a refactor navigator from diagnostics."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Final, TypedDict

from ..core.models import Diagnostic, RunResult
from ..interfaces.analysis import AnnotationProvider, FunctionScaleEstimator
from .services import resolve_function_scale_estimator

MAX_NAVIGATOR_ENTRIES: Final[int] = 10
COMPLEXITY_CODES: Final[set[str]] = {"C901", "R0915", "PLR0915", "R1260"}
COMPLEXITY_SIGNATURES: Final[set[str]] = {"complex", "complexity", "statement"}
TYPING_CODES_PREFIX: Final[str] = "ANN"
TYPING_SIGNATURES: Final[set[str]] = {"annotation", "typed"}
DOCUMENTATION_CODES_PREFIX: Final[str] = "D1"
DOCUMENTATION_SIGNATURES: Final[set[str]] = {"docstring"}
MAGIC_CODES: Final[set[str]] = {"PLR2004", "R2004"}
MAGIC_SIGNATURES: Final[set[str]] = {"magic"}


class IssueTag(str, Enum):
    """Enumerate recognised navigator issue tags."""

    COMPLEXITY = "complexity"
    TYPING = "typing"
    DOCUMENTATION = "documentation"
    MAGIC_NUMBER = "magic-number"


class NavigatorDiagnosticPayload(TypedDict):
    """Typed representation of diagnostic details within the navigator."""

    tool: str
    code: str
    message: str
    line: int | None
    severity: str


class NavigatorPayload(TypedDict):
    """Typed representation of a refactor navigator entry."""

    file: str
    function: str
    issue_tags: dict[str, int]
    size: int | None
    complexity: int | None
    diagnostics: list[NavigatorDiagnosticPayload]


@dataclass(slots=True)
class NavigatorDiagnosticEntry:
    """Describe a diagnostic included in the refactor navigator payload."""

    tool: str
    code: str
    message: str
    line: int | None
    severity: str

    def to_payload(self) -> NavigatorDiagnosticPayload:
        """Return a serialisable mapping for the diagnostic entry."""

        return NavigatorDiagnosticPayload(
            tool=self.tool,
            code=self.code,
            message=self.message,
            line=self.line,
            severity=self.severity,
        )


@dataclass(slots=True)
class NavigatorBucket:
    """Collect diagnostics and metadata for a refactoring hotspot."""

    file: str = ""
    function: str = ""
    issue_tags: Counter[IssueTag] = field(default_factory=Counter)
    size: int | None = None
    complexity: int | None = None
    diagnostics: list[NavigatorDiagnosticEntry] = field(default_factory=list)

    def add_diagnostic(self, diag: Diagnostic, tag: IssueTag | None) -> None:
        """Record ``diag`` in the bucket and increment the associated tag."""

        self.file = diag.file or self.file
        self.function = diag.function or self.function
        if tag is not None:
            self.issue_tags[tag] += 1
        self.diagnostics.append(
            NavigatorDiagnosticEntry(
                tool=diag.tool,
                code=diag.code or "",
                message=diag.message,
                line=diag.line,
                severity=diag.severity.value,
            ),
        )

    @property
    def total_issue_count(self) -> int:
        """Return the total number of issues aggregated under this bucket."""

        return sum(self.issue_tags.values())

    def to_payload(self) -> NavigatorPayload:
        """Return a serialisable payload representing this bucket."""

        return NavigatorPayload(
            file=self.file,
            function=self.function,
            issue_tags={tag.value: count for tag, count in self.issue_tags.items()},
            size=self.size,
            complexity=self.complexity,
            diagnostics=[entry.to_payload() for entry in self.diagnostics],
        )


def build_refactor_navigator(
    result: RunResult,
    engine: AnnotationProvider,
    *,
    function_scale: FunctionScaleEstimator | None = None,
) -> None:
    """Populate ``result.analysis['refactor_navigator']`` with hotspot data.

    Args:
        result: Run outcome containing diagnostics and analysis metadata.
        engine: Annotation engine used to derive diagnostic message signatures.
        function_scale: Optional estimator used to approximate function size and
            complexity for navigator prioritisation. When omitted, the
            registered function scale estimator service is resolved.
    """

    estimator = function_scale or resolve_function_scale_estimator()
    hotspots: defaultdict[tuple[str, str], NavigatorBucket] = defaultdict(NavigatorBucket)

    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            tag = _issue_tag(diag, engine)
            if tag is not None:
                diag.tags = tuple(sorted({*diag.tags, tag.value}))
            bucket = hotspots[(diag.file or "", diag.function or "")]
            bucket.add_diagnostic(diag, tag)

    summary: list[NavigatorBucket] = []
    root_path = Path(result.root)
    for (file_path, function), bucket in hotspots.items():
        if not bucket.issue_tags:
            continue
        size, complexity = estimator.estimate(root_path / file_path, function)
        bucket.size = size
        bucket.complexity = complexity
        summary.append(bucket)

    summary.sort(
        key=lambda bucket: (
            -bucket.total_issue_count,
            -(bucket.size or 0),
            f"{bucket.file}::{bucket.function}",
        ),
    )
    result.analysis["refactor_navigator"] = [bucket.to_payload() for bucket in summary[:MAX_NAVIGATOR_ENTRIES]]


def _issue_tag(diag: Diagnostic, engine: AnnotationProvider) -> IssueTag | None:
    """Return the navigator issue tag for ``diag`` when recognised."""

    code = (diag.code or "").upper()
    signature = set(engine.message_signature(diag.message))

    if code in COMPLEXITY_CODES or COMPLEXITY_SIGNATURES & signature:
        return IssueTag.COMPLEXITY
    if code.startswith(TYPING_CODES_PREFIX) or TYPING_SIGNATURES & signature:
        return IssueTag.TYPING
    if DOCUMENTATION_SIGNATURES & signature or code.startswith(DOCUMENTATION_CODES_PREFIX):
        return IssueTag.DOCUMENTATION
    if code in MAGIC_CODES or MAGIC_SIGNATURES & signature:
        return IssueTag.MAGIC_NUMBER
    return None


__all__ = ["build_refactor_navigator"]
