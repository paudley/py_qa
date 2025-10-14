# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Helpers for resolving analysis-layer services via the DI container."""

from __future__ import annotations

from enum import Enum
from functools import cache
from typing import Final, cast

from ..core.runtime import ServiceContainer, register_default_services
from ..interfaces.analysis import AnnotationProvider, ContextResolver, FunctionScaleEstimator
from .bootstrap import register_analysis_services


@cache
def _default_services() -> ServiceContainer:
    """Build the default analysis service container.

    Returns:
        ServiceContainer: Container with baseline runtime and analysis bindings
        registered.
    """

    container = ServiceContainer()
    register_default_services(container)
    register_analysis_services(container)
    return container


class _ContainerSelector(Enum):
    """Provide sentinel values for container selection."""

    DEFAULT_ANALYSIS = "default-analysis-services"


DEFAULT_ANALYSIS_CONTAINER: Final = _ContainerSelector.DEFAULT_ANALYSIS


def _select_container(container: ServiceContainer | _ContainerSelector) -> ServiceContainer:
    """Choose the service container to use for analysis lookups.

    Args:
        container: Existing runtime container or the `DEFAULT_ANALYSIS_CONTAINER`
            sentinel requesting the lazily constructed default container.

    Returns:
        ServiceContainer: Container that should supply service instances.
    """

    if isinstance(container, ServiceContainer):
        return container
    return _default_services()


def resolve_annotation_provider(
    container: ServiceContainer | _ContainerSelector = DEFAULT_ANALYSIS_CONTAINER,
) -> AnnotationProvider:
    """Fetch the registered annotation provider implementation.

    Args:
        container: Runtime container to query. Pass
            `DEFAULT_ANALYSIS_CONTAINER` (the default) to reuse the lazily
            cached analysis container.

    Returns:
        AnnotationProvider: Implementation registered under
        ``"annotation_provider"``.
    """

    services = _select_container(container)
    resolved = services.resolve("annotation_provider")
    return cast(AnnotationProvider, resolved)


def resolve_function_scale_estimator(
    container: ServiceContainer | _ContainerSelector = DEFAULT_ANALYSIS_CONTAINER,
) -> FunctionScaleEstimator:
    """Fetch the registered function scale estimator implementation.

    Args:
        container: Runtime container to query. Pass
            `DEFAULT_ANALYSIS_CONTAINER` (the default) to reuse the lazily
            cached analysis container.

    Returns:
        FunctionScaleEstimator: Implementation bound to
        ``"function_scale_estimator"``.
    """

    services = _select_container(container)
    resolved = services.resolve("function_scale_estimator")
    return cast(FunctionScaleEstimator, resolved)


def resolve_context_resolver(
    container: ServiceContainer | _ContainerSelector = DEFAULT_ANALYSIS_CONTAINER,
) -> ContextResolver:
    """Fetch the registered Tree-sitter context resolver implementation.

    Args:
        container: Runtime container to query. Pass
            `DEFAULT_ANALYSIS_CONTAINER` (the default) to reuse the lazily
            cached analysis container.

    Returns:
        ContextResolver: Implementation bound to ``"context_resolver"``.
    """

    services = _select_container(container)
    resolved = services.resolve("context_resolver")
    return cast(ContextResolver, resolved)


__all__ = [
    "resolve_annotation_provider",
    "resolve_context_resolver",
    "resolve_function_scale_estimator",
]
