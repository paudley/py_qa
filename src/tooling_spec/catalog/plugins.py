# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Entry-point helpers for standalone catalog plugins."""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import TypeAlias, TypeVar, cast

from .errors import CatalogIntegrityError
from .model_catalog import CatalogFragment
from .model_strategy import StrategyDefinition
from .model_tool import ToolDefinition
from .utils import thaw_json_value

PLUGIN_GROUP = "pyqa.catalog.plugins"


@dataclass(frozen=True, slots=True)
class CatalogPluginContext:
    """Execution context shared with catalog plugin factories."""

    catalog_root: Path
    schema_root: Path
    fragments: tuple[CatalogFragment, ...]
    strategies: tuple[StrategyDefinition, ...]
    tools: tuple[ToolDefinition, ...]
    checksum: str


@dataclass(frozen=True, slots=True)
class CatalogContribution:
    """Payload contributed by a catalog plugin."""

    fragments: tuple[CatalogFragment, ...] = ()
    strategies: tuple[StrategyDefinition, ...] = ()
    tools: tuple[ToolDefinition, ...] = ()

    def is_empty(self) -> bool:
        """Return ``True`` when the contribution is empty."""

        return not (self.fragments or self.strategies or self.tools)


PluginFactory: TypeAlias = Callable[..., CatalogContribution | None]


def load_plugin_contributions(
    context: CatalogPluginContext,
    *,
    plugin_factories: Sequence[PluginFactory] | None = None,
) -> tuple[CatalogContribution, ...]:
    """Return contributions sourced from discovered catalog plugins."""

    factories: Sequence[PluginFactory]
    if plugin_factories is not None:
        factories = plugin_factories
    else:
        factories = _discover_plugin_factories()
    contributions: list[CatalogContribution] = []
    for factory in factories:
        contribution = _invoke_plugin(factory, context)
        if contribution is None or contribution.is_empty():
            continue
        contributions.append(contribution)
    return tuple(contributions)


def merge_contributions(
    *,
    base_fragments: Sequence[CatalogFragment],
    base_strategies: Sequence[StrategyDefinition],
    base_tools: Sequence[ToolDefinition],
    contributions: Sequence[CatalogContribution],
) -> tuple[tuple[CatalogFragment, ...], tuple[StrategyDefinition, ...], tuple[ToolDefinition, ...]]:
    """Merge plugin contributions with base catalog data."""

    merged_fragments = _merge_unique(
        base_fragments,
        (fragment for contribution in contributions for fragment in contribution.fragments),
        key=lambda fragment: fragment.name,
        description="fragment",
    )
    merged_strategies = _merge_unique(
        base_strategies,
        (strategy for contribution in contributions for strategy in contribution.strategies),
        key=lambda strategy: strategy.identifier,
        description="strategy",
    )
    merged_tools = _merge_unique(
        base_tools,
        (tool for contribution in contributions for tool in contribution.tools),
        key=lambda tool: tool.name,
        description="tool",
    )
    return merged_fragments, merged_strategies, merged_tools


def combine_checksums(base_checksum: str, contributions: Sequence[CatalogContribution]) -> str:
    """Return a checksum that incorporates plugin contributions."""

    if not contributions:
        return base_checksum

    hasher = hashlib.sha256()
    hasher.update(base_checksum.encode("utf-8"))
    hasher.update(_serialise_contributions(contributions))
    return hasher.hexdigest()


def _discover_plugin_factories() -> tuple[PluginFactory, ...]:
    try:
        entries = metadata.entry_points()
    except metadata.PackageNotFoundError:  # pragma: no cover - metadata failure fallback
        return ()
    selected = entries.select(group=PLUGIN_GROUP)
    factories: list[PluginFactory] = []
    for entry in selected:
        try:
            factories.append(cast(PluginFactory, entry.load()))
        except (AttributeError, ImportError, ValueError):
            continue
    return tuple(factories)


def _invoke_plugin(factory: PluginFactory, context: CatalogPluginContext) -> CatalogContribution | None:
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):  # pragma: no cover - C extensions without metadata
        signature = None

    if signature is None or not signature.parameters:
        result = factory()
    else:
        try:
            result = factory(context)
        except TypeError as error:
            if _accepts_no_arguments(signature):
                result = factory()
            else:  # pragma: no cover - genuine plugin error
                raise error

    if result is None:
        return None
    if not isinstance(result, CatalogContribution):
        raise CatalogIntegrityError(f"Catalog plugin {factory!r} did not return a CatalogContribution")
    return result


def _accepts_no_arguments(signature: inspect.Signature) -> bool:
    return not signature.parameters or all(
        parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for parameter in signature.parameters.values()
    )


def _merge_unique(
    base: Sequence[_T],
    additions: Iterable[_T],
    *,
    key: Callable[[_T], str],
    description: str,
) -> tuple[_T, ...]:
    merged = list(base)
    seen = {key(item) for item in base}
    for item in additions:
        identifier = key(item)
        if identifier in seen:
            raise CatalogIntegrityError(
                f"Catalog plugin attempted to register duplicate {description} '{identifier}'",
            )
        seen.add(identifier)
        merged.append(item)
    return tuple(merged)


def _serialise_contributions(contributions: Sequence[CatalogContribution]) -> bytes:
    payload = []
    for contribution in contributions:
        payload.append(
            {
                "fragments": [
                    {
                        "name": fragment.name,
                        "data": thaw_json_value(fragment.data),
                    }
                    for fragment in contribution.fragments
                ],
                "strategies": [
                    {
                        "identifier": strategy.identifier,
                        "payload": thaw_json_value(strategy.to_dict()),
                    }
                    for strategy in contribution.strategies
                ],
                "tools": [
                    {
                        "name": tool.name,
                        "payload": thaw_json_value(tool.to_dict()),
                    }
                    for tool in contribution.tools
                ],
            },
        )
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


_T = TypeVar("_T", ToolDefinition, StrategyDefinition, CatalogFragment)


__all__ = [
    "CatalogContribution",
    "CatalogPluginContext",
    "combine_checksums",
    "load_plugin_contributions",
    "merge_contributions",
]
