# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Service registration helpers for analysis-level components."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from ..core.metrics.function_scale import FunctionScaleEstimatorService
from ..interfaces.runtime import ServiceFactory, ServiceProtocol, ServiceRegistryProtocol
from .annotations import AnnotationEngine
from .treesitter import TreeSitterContextResolver


def _context_resolver_factory(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the default Tree-sitter context resolver factory.

    Args:
        _ : Unused service registry required by the factory signature.

    Returns:
        ServiceProtocol: Tree-sitter context resolver instance.
    """

    return TreeSitterContextResolver()


def _annotation_engine_factory(services: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the annotation engine configured with the registered resolver.

    Args:
        services: Service registry providing access to previously registered collaborators.

    Returns:
        ServiceProtocol: Annotation engine wired with the context resolver.
    """

    resolver = services.resolve("context_resolver")
    return AnnotationEngine(
        context_resolver=cast(TreeSitterContextResolver, resolver),
    )


def _function_scale_factory(_: ServiceRegistryProtocol) -> ServiceProtocol:
    """Return the function scale estimator service factory.

    Args:
        _ : Unused service registry placeholder for signature compatibility.

    Returns:
        ServiceProtocol: Function scale estimator concrete instance.
    """

    return FunctionScaleEstimatorService()


def register_analysis_services(container: ServiceRegistryProtocol) -> None:
    """Register analysis-layer services with ``container``.

    Args:
        container: Dependency injection interface receiving analysis services.
    """

    if "context_resolver" not in container:
        container.register("context_resolver", _AnalysisServiceFactory("context_resolver", _context_resolver_factory))
    if "annotation_provider" not in container:
        container.register(
            "annotation_provider",
            _AnalysisServiceFactory("annotation_provider", _annotation_engine_factory),
        )
    if "function_scale_estimator" not in container:
        container.register(
            "function_scale_estimator",
            _AnalysisServiceFactory("function_scale_estimator", _function_scale_factory),
        )


__all__ = ["register_analysis_services"]


@dataclass(slots=True, frozen=True)
class _AnalysisServiceFactory(ServiceFactory):
    """Static service factory used to register analysis components."""

    name: str
    builder: Callable[[ServiceRegistryProtocol], ServiceProtocol]

    def __call__(self, container: ServiceRegistryProtocol) -> ServiceProtocol:
        """Return the service produced by :attr:`builder`.

        Args:
            container: Service registry supplying dependent services.

        Returns:
            ServiceProtocol: Service instance produced by the builder.
        """

        return self.builder(container)

    def __repr__(self) -> str:
        """Return a diagnostic representation for debugging.

        Returns:
            str: Identifier referencing the factory name.
        """

        return f"analysis_factory({self.name})"
