# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Plugin adapters that bind runtime catalogue logic to tooling specs."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from tooling_spec.catalog import plugins as _spec_plugins

from ..plugins import load_catalog_plugins

CatalogContribution = _spec_plugins.CatalogContribution
CatalogPluginContext = _spec_plugins.CatalogPluginContext
combine_checksums = _spec_plugins.combine_checksums
merge_contributions = _spec_plugins.merge_contributions

__all__ = (
    "combine_checksums",
    "merge_contributions",
    "CatalogContribution",
    "CatalogPluginContext",
    "load_plugin_contributions",
)


def load_plugin_contributions(
    context: CatalogPluginContext,
    *,
    plugin_factories: Sequence[Callable[..., CatalogContribution]] | None = None,
) -> tuple[CatalogContribution, ...]:
    """Collect catalog contributions sourced from entry-point plugins.

    Args:
        context: Execution context shared with plugin factories.
        plugin_factories: Optional override of plugin factories. When omitted the
            entry-point group ``pyqa.catalog.plugins`` discovered by
            :func:`pyqa.plugins.load_catalog_plugins` is used.

    Returns:
        tuple[CatalogContribution, ...]: Ordered contributions supplied by
        plugin factories.
    """

    factories = tuple(plugin_factories) if plugin_factories is not None else load_catalog_plugins()
    return _spec_plugins.load_plugin_contributions(context, plugin_factories=factories)
