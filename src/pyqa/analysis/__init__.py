# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Higher-level analysis passes that enrich diagnostics with metadata."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import-time assistance only
    from .annotations import AnnotationEngine, MessageSpan
    from .change_impact import apply_change_impact
    from .navigator import build_refactor_navigator
    from .suppression import apply_suppression_hints

__all__ = [
    "AnnotationEngine",
    "MessageSpan",
    "apply_change_impact",
    "build_refactor_navigator",
    "apply_suppression_hints",
]

_EXPORT_MAP: dict[str, tuple[str, str]] = {
    "AnnotationEngine": ("pyqa.analysis.annotations", "AnnotationEngine"),
    "MessageSpan": ("pyqa.analysis.annotations", "MessageSpan"),
    "apply_change_impact": ("pyqa.analysis.change_impact", "apply_change_impact"),
    "build_refactor_navigator": ("pyqa.analysis.navigator", "build_refactor_navigator"),
    "apply_suppression_hints": ("pyqa.analysis.suppression", "apply_suppression_hints"),
}


def __getattr__(name: str) -> Any:
    """Lazily import heavy analysis modules on demand."""

    try:
        module_name, attribute = _EXPORT_MAP[name]
    except KeyError as exc:  # pragma: no cover - mirrors default behaviour
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = import_module(module_name)
    value = getattr(module, attribute)
    globals()[name] = value
    return value
