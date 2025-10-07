# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Protocols describing diagnostic processing pipelines."""

# pylint: disable=too-few-public-methods -- Protocol definitions intentionally expose minimal method surfaces.

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from pyqa.core.severity import SeverityRuleView

from ..core.models import Diagnostic, RawDiagnostic


@dataclass(frozen=True, slots=True)
class DiagnosticPipelineRequest:
    """Request bundle consumed by diagnostic pipelines."""

    tool_name: str
    candidates: Sequence[RawDiagnostic | Diagnostic]
    severity_rules: SeverityRuleView
    suppression_patterns: Sequence[str]
    project_root: Path


@runtime_checkable
class DiagnosticPipeline(Protocol):
    """Process raw diagnostics into filtered results for consumption."""

    def run(self, request: DiagnosticPipelineRequest) -> list[Diagnostic]:
        """Return filtered diagnostics ready for presentation."""

        raise NotImplementedError


__all__ = ["DiagnosticPipeline", "DiagnosticPipelineRequest"]
