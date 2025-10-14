# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Helpers for resolving analysis-layer services via the DI container."""

from __future__ import annotations

from functools import cache
from typing import cast

from ..core.runtime import ServiceContainer, register_default_services
from ..interfaces.analysis import AnnotationProvider, ContextResolver, FunctionScaleEstimator
from .bootstrap import register_analysis_services


@cache
def _default_services() -> ServiceContainer:
    """Return a lazily initialised container with analysis registrations."""

    container = ServiceContainer()
    register_default_services(container)
    register_analysis_services(container)
    return container


def resolve_annotation_provider(container: ServiceContainer | None = None) -> AnnotationProvider:
    """Return the registered annotation provider implementation."""

    services = container or _default_services()
    provider = services.resolve("annotation_provider")
    return cast(AnnotationProvider, provider)


def resolve_function_scale_estimator(
    container: ServiceContainer | None = None,
) -> FunctionScaleEstimator:
    """Return the registered function scale estimator implementation."""

    services = container or _default_services()
    estimator = services.resolve("function_scale_estimator")
    return cast(FunctionScaleEstimator, estimator)


def resolve_context_resolver(container: ServiceContainer | None = None) -> ContextResolver:
    """Return the registered Tree-sitter context resolver implementation."""

    services = container or _default_services()
    resolver = services.resolve("context_resolver")
    return cast(ContextResolver, resolver)


__all__ = [
    "resolve_annotation_provider",
    "resolve_context_resolver",
    "resolve_function_scale_estimator",
]
