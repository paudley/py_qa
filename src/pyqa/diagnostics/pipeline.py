# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Composable diagnostic processing pipeline."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pyqa.core.severity import SeverityRuleView

from ..core.models import Diagnostic, RawDiagnostic
from ..interfaces.diagnostics import DiagnosticPipeline as DiagnosticPipelineProtocol
from ..interfaces.diagnostics import (
    DiagnosticPipelineRequest,
)
from .core import normalize_diagnostics
from .filtering import filter_diagnostics

Normalizer = Callable[[Sequence[RawDiagnostic | Diagnostic], str, SeverityRuleView], list[Diagnostic]]
Filterer = Callable[[Sequence[Diagnostic], str, Sequence[str], DiagnosticPipelineRequest], list[Diagnostic]]


def _default_normalizer(
    candidates: Sequence[RawDiagnostic | Diagnostic],
    tool_name: str,
    severity_rules: SeverityRuleView,
) -> list[Diagnostic]:
    """Return diagnostics normalised using the default strategy.

    Args:
        candidates: Raw or canonical diagnostics produced by a tool.
        tool_name: Name of the tool associated with ``candidates``.
        severity_rules: Severity rule view used to adjust diagnostic severity.

    Returns:
        list[Diagnostic]: Normalised diagnostics ready for filtering.
    """
    return normalize_diagnostics(candidates, tool_name=tool_name, severity_rules=severity_rules)


def _default_filter(
    diagnostics: Sequence[Diagnostic],
    tool_name: str,
    suppression_patterns: Sequence[str],
    request: DiagnosticPipelineRequest,
) -> list[Diagnostic]:
    """Filter diagnostics using the default suppression heuristics.

    Args:
        diagnostics: Normalised diagnostics emitted by the pipeline.
        tool_name: Name of the originating tool.
        suppression_patterns: Regular expression patterns provided by the caller.
        request: Pipeline request containing metadata such as the project root.

    Returns:
        list[Diagnostic]: Diagnostics that should be surfaced to the caller.
    """
    return filter_diagnostics(diagnostics, tool_name, suppression_patterns, request.project_root)


@dataclass(slots=True)
class DiagnosticPipeline(DiagnosticPipelineProtocol):
    """Pipeline that normalises raw diagnostics and applies filtering.

    Attributes:
        normalize: Callable responsible for converting raw diagnostics into
            canonical models.
        filter: Callable responsible for suppressing diagnostics according to
            request configuration.
    """

    normalize: Normalizer = _default_normalizer
    filter: Filterer = _default_filter

    @property
    def pipeline_name(self) -> str:
        """Return the identifier for this diagnostic pipeline.

        Returns:
            str: Human-readable identifier for the pipeline implementation.
        """

        return "default"

    def run(self, request: DiagnosticPipelineRequest) -> list[Diagnostic]:
        """Execute the pipeline and return the retained diagnostics.

        Args:
            request: Pipeline request describing candidates, tool metadata, and
                suppression configuration.

        Returns:
            list[Diagnostic]: Diagnostics that pass normalisation and filtering.
        """

        normalized = self.normalize(request.candidates, request.tool_name, request.severity_rules)
        return self.filter(normalized, request.tool_name, request.suppression_patterns, request)


__all__ = ["DiagnosticPipeline"]
