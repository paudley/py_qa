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
    """Represent the execution context shared with catalog plugins."""

    catalog_root: Path
    schema_root: Path
    fragments: tuple[CatalogFragment, ...]
    strategies: tuple[StrategyDefinition, ...]
    tools: tuple[ToolDefinition, ...]
    checksum: str


@dataclass(frozen=True, slots=True)
class CatalogContribution:
    """Represent the payload contributed by a catalog plugin."""

    fragments: tuple[CatalogFragment, ...] = ()
    strategies: tuple[StrategyDefinition, ...] = ()
    tools: tuple[ToolDefinition, ...] = ()

    def is_empty(self) -> bool:
        """Return ``True`` when this contribution contains no artifacts.

        Returns:
            bool: ``True`` when the contribution has no fragments, strategies, or tools.
        """

        return not (self.fragments or self.strategies or self.tools)


PluginFactory: TypeAlias = Callable[..., CatalogContribution | None]


def load_plugin_contributions(
    context: CatalogPluginContext,
    *,
    plugin_factories: Sequence[PluginFactory] | None = None,
) -> tuple[CatalogContribution, ...]:
    """Load plugin contributions from the registered entry points.

    Args:
        context: Execution context passed to each plugin factory.
        plugin_factories: Optional factory overrides used for testing.

    Returns:
        tuple[CatalogContribution, ...]: Contributions emitted by the factories.
    """

    factories: Sequence[PluginFactory] = (
        plugin_factories if plugin_factories is not None else _discover_plugin_factories()
    )
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
    """Merge plugin contributions with the baseline catalog artifacts.

    Args:
        base_fragments: Fragments supplied by the base catalog snapshot.
        base_strategies: Strategy definitions provided by the base catalog.
        base_tools: Tool definitions present in the base catalog.
        contributions: Plugin contributions to merge into the base artifacts.

    Returns:
        tuple: Merged fragments, strategies, and tools preserving original order.

    Raises:
        CatalogIntegrityError: If a plugin attempts to register a duplicate entry.
    """

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
    """Combine the base checksum with plugin contributions.

    Args:
        base_checksum: Hash representing the baseline catalog snapshot.
        contributions: Plugin contributions included in the final catalog.

    Returns:
        str: Deterministic checksum incorporating plugin payloads.
    """

    if not contributions:
        return base_checksum

    hasher = hashlib.sha256()
    hasher.update(base_checksum.encode("utf-8"))
    hasher.update(_serialise_contributions(contributions))
    return hasher.hexdigest()


def _discover_plugin_factories() -> tuple[PluginFactory, ...]:
    """Discover plugin factories registered under the catalog entry point.

    Returns:
        tuple[PluginFactory, ...]: Tuple of discovered plugin factories.
    """
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
    """Invoke ``factory`` with the appropriate calling convention.

    Args:
        factory: Plugin factory callable discovered from entry points.
        context: Execution context supplied to the plugin.

    Returns:
        CatalogContribution | None: Contribution emitted by the plugin, or ``None`` when skipped.

    Raises:
        CatalogIntegrityError: If the plugin returns an unexpected payload type.
    """
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
    """Return ``True`` when ``signature`` accepts no positional arguments.

    Args:
        signature: Signature reported by the candidate plugin factory.

    Returns:
        bool: ``True`` if the factory can be invoked without arguments.
    """

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
    """Merge ``additions`` into ``base`` ensuring keys remain unique.

    Args:
        base: Existing sequence of catalog artifacts.
        additions: Additional artifacts contributed by plugins.
        key: Callable returning the unique identifier for an artifact.
        description: Human-readable description used in error messages.

    Returns:
        tuple[_T, ...]: Combined sequence preserving the order of additions.

    Raises:
        CatalogIntegrityError: If a duplicate identifier is encountered.
    """

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
    """Serialise contributions into bytes for checksum generation.

    Args:
        contributions: Contributions to serialise for hashing.

    Returns:
        bytes: UTF-8 encoded JSON payload representing the contributions.
    """

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
