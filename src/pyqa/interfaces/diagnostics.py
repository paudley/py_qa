# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Protocols describing diagnostic processing pipelines."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from pyqa.core.severity import SeverityRuleView

from ..core.models import Diagnostic, RawDiagnostic


@dataclass(frozen=True, slots=True)
class DiagnosticPipelineRequest:
    """Represent a request bundle consumed by diagnostic pipelines."""

    tool_name: str
    candidates: Sequence[RawDiagnostic | Diagnostic]
    severity_rules: SeverityRuleView
    suppression_patterns: Sequence[str]
    project_root: Path


@runtime_checkable
class DiagnosticPipeline(Protocol):
    """Process raw diagnostics into filtered results for consumption."""

    @property
    @abstractmethod
    def pipeline_name(self) -> str:
        """Return the identifier of the pipeline implementation.

        Returns:
            str: Identifier describing the diagnostic pipeline implementation.
        """
        raise NotImplementedError

    @abstractmethod
    def run(self, request: DiagnosticPipelineRequest) -> list[Diagnostic]:
        """Produce filtered diagnostics ready for presentation.

        Args:
            request: Pipeline request containing raw diagnostics and metadata.

        Returns:
            list[Diagnostic]: Diagnostics normalised and filtered by the pipeline.
        """
        raise NotImplementedError


__all__ = ["DiagnosticPipeline", "DiagnosticPipelineRequest"]
