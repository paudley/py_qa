# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""High-level annotation engine utilities."""

from __future__ import annotations

from ...interfaces.analysis import SimpleMessageSpan as MessageSpan
from .engine import AnnotationEngine, DiagnosticAnnotation, HighlightKind, MessageAnalysis

__all__ = [
    "AnnotationEngine",
    "HighlightKind",
    "DiagnosticAnnotation",
    "MessageAnalysis",
    "MessageSpan",
]
