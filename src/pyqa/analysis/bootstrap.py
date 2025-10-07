# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Service registration helpers for analysis-level components."""

from __future__ import annotations

from ..core.metrics.function_scale import FunctionScaleEstimatorService
from ..core.runtime import ServiceContainer
from .annotations import AnnotationEngine
from .treesitter import TreeSitterContextResolver


def register_analysis_services(container: ServiceContainer) -> None:
    """Register analysis-layer services with ``container``.

    Args:
        container: Dependency injection container receiving analysis services.
    """

    container.register(
        "context_resolver",
        lambda _: TreeSitterContextResolver(),
    )
    container.register(
        "annotation_provider",
        lambda services: AnnotationEngine(
            context_resolver=services.resolve("context_resolver"),
        ),
    )
    container.register(
        "function_scale_estimator",
        lambda _: FunctionScaleEstimatorService(),
    )


__all__ = ["register_analysis_services"]
