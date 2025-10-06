# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Tool metadata and helper utilities for catalog entries."""

from __future__ import annotations

from typing import Final

from tooling_spec.catalog import model_tool as _spec_model_tool

TOOL_MODEL_EXPORTS = _spec_model_tool.TOOL_MODEL_EXPORTS
TOOL_MODEL_OBJECTS = _spec_model_tool.TOOL_MODEL_OBJECTS
ToolBehaviour = _spec_model_tool.ToolBehaviour
ToolDefinition = _spec_model_tool.ToolDefinition
ToolComponents = _spec_model_tool.ToolComponents
ToolFiles = _spec_model_tool.ToolFiles
ToolIdentity = _spec_model_tool.ToolIdentity
ToolMetadata = _spec_model_tool.ToolMetadata
ToolOrdering = _spec_model_tool.ToolOrdering
parse_documentation_bundle = _spec_model_tool.parse_documentation_bundle
parse_runtime_definition = _spec_model_tool.parse_runtime_definition
parse_tool_metadata = _spec_model_tool.parse_tool_metadata

__all__: Final[tuple[str, ...]] = (
    "parse_tool_metadata",
    "parse_runtime_definition",
    "parse_documentation_bundle",
    "ToolOrdering",
    "ToolMetadata",
    "ToolIdentity",
    "ToolFiles",
    "ToolDefinition",
    "ToolComponents",
    "ToolBehaviour",
    "TOOL_MODEL_OBJECTS",
    "TOOL_MODEL_EXPORTS",
)
