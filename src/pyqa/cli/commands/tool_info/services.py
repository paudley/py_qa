# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Service helpers for the tool-info CLI implementation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, cast

from pyqa.core.config.loader import ConfigError, ConfigLoader, FieldUpdate
from pyqa.interfaces.config import Config as ConfigProtocol

from ....catalog.model_catalog import CatalogSnapshot
from ....catalog.model_tool import ToolDefinition
from ....tools.base import Tool
from ....tools.builtins import initialize_registry
from ....tools.registry import DEFAULT_REGISTRY
from ...core.shared import CLIError, CLILogger
from ...core.utils import check_tool_status
from .models import ToolInfoConfigData, ToolInfoContext, ToolInfoInputs


def load_configuration(
    inputs: ToolInfoInputs,
    *,
    logger: CLILogger,
) -> ToolInfoConfigData:
    """Load configuration for tool-info rendering.

    Args:
        inputs: Normalized CLI inputs containing the project root and console.
        logger: CLI logger used to emit configuration failure messages.

    Returns:
        ToolInfoConfigData: Loaded configuration bundle.

    Raises:
        CLIError: Raised when configuration loading fails.
    """

    if inputs.cfg is not None:
        return ToolInfoConfigData(config=inputs.cfg, warnings=(), updates=())

    loader = ConfigLoader.for_root(inputs.root)
    try:
        load_result = loader.load_with_trace()
    except ConfigError as exc:  # pragma: no cover - CLI path
        message = f"Failed to load configuration: {exc}"
        logger.fail(message)
        raise CLIError(message) from exc

    return ToolInfoConfigData(
        config=cast(ConfigProtocol, load_result.config),
        warnings=tuple(load_result.warnings),
        updates=tuple(load_result.updates),
    )


def resolve_catalog_snapshot(inputs: ToolInfoInputs) -> CatalogSnapshot:
    """Return the catalog snapshot used for rendering.

    Args:
        inputs: Normalized CLI inputs including an optional snapshot.

    Returns:
        CatalogSnapshot: Available tool metadata.
    """

    snapshot = inputs.catalog_snapshot
    if snapshot is not None:
        return snapshot
    return initialize_registry(registry=DEFAULT_REGISTRY)


def resolve_tool(inputs: ToolInfoInputs, *, logger: CLILogger) -> Tool:
    """Return the registry tool definition.

    Args:
        inputs: Normalized CLI inputs describing the requested tool.
        logger: CLI logger used to emit failure messages when no tool matches.

    Returns:
        Tool: Tool definition resolved from the registry.

    Raises:
        CLIError: Raised when the tool cannot be located.
    """

    tool = DEFAULT_REGISTRY.try_get(inputs.tool_name)
    if tool is None:
        message = f"Unknown tool: {inputs.tool_name}"
        logger.fail(message)
        raise CLIError(message)
    return tool


def find_catalog_tool(name: str, snapshot: CatalogSnapshot | None) -> ToolDefinition | None:
    """Return the catalog definition matching ``name`` when present.

    Args:
        name: Tool name to search for.
        snapshot: Catalog snapshot containing available definitions.

    Returns:
        ToolDefinition | None: Matching definition when found, otherwise ``None``.
    """

    if snapshot is None:
        return None
    for definition in snapshot.tools:
        if definition.name == name or name in definition.aliases:
            return definition
    return None


def prepare_context(inputs: ToolInfoInputs, *, logger: CLILogger) -> ToolInfoContext:
    """Return a fully populated context for rendering tool information.

    Args:
        inputs: Normalized CLI inputs describing the requested tool.
        logger: CLI logger used for configuration and tool resolution failures.

    Returns:
        ToolInfoContext: Context containing configuration, status, and metadata.
    """

    config_data = load_configuration(inputs, logger=logger)
    snapshot = resolve_catalog_snapshot(inputs)
    tool = resolve_tool(inputs, logger=logger)
    status = check_tool_status(tool)
    config_model = config_data.config
    tool_settings = config_model.tool_settings
    overrides = dict(tool_settings.get(tool.name, {}) or {})
    catalog_tool = find_catalog_tool(tool.name, snapshot)

    return ToolInfoContext(
        inputs=inputs,
        config=config_data,
        tool=tool,
        status=status,
        overrides=overrides,
        catalog_snapshot=snapshot,
        catalog_tool=catalog_tool,
    )


TOOL_SETTINGS_SECTION: Final[str] = "tool_settings"


def provenance_updates_for_tool(
    *,
    updates: Sequence[FieldUpdate],
    tool_name: str,
) -> tuple[FieldUpdate, ...]:
    """Return configuration provenance updates affecting the tool.

    Args:
        updates: Sequence of configuration field updates.
        tool_name: Tool identifier used to filter updates.

    Returns:
        tuple[FieldUpdate, ...]: Filtered updates relevant to ``tool_name``.
    """

    return tuple(update for update in updates if update.section == TOOL_SETTINGS_SECTION and update.field == tool_name)


__all__ = [
    "find_catalog_tool",
    "load_configuration",
    "prepare_context",
    "provenance_updates_for_tool",
    "resolve_catalog_snapshot",
    "resolve_tool",
]
