# SPDX-License-Identifier: MIT
"""Tool metadata and helper utilities for catalog entries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .errors import CatalogIntegrityError
from .model_actions import ActionDefinition, actions_array
from .model_diagnostics import DiagnosticsBundle
from .model_documentation import DocumentationBundle
from .model_options import OptionDefinition, options_array
from .model_runtime import RuntimeDefinition
from .types import TOOL_SCHEMA_VERSION, JSONValue
from .utils import expect_mapping, expect_string, optional_bool, string_array


@dataclass(frozen=True, slots=True)
class ToolIdentity:
    """Core identifying information for a tool definition."""

    name: str
    aliases: tuple[str, ...]
    description: str
    languages: tuple[str, ...]
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolBehaviour:
    """Behaviour flags controlling default enablement and installation."""

    default_enabled: bool
    auto_install: bool


@dataclass(frozen=True, slots=True)
class ToolOrdering:
    """Phase ordering metadata for a tool."""

    phase: str
    before: tuple[str, ...]
    after: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolFiles:
    """File extension and config file metadata for a tool."""

    file_extensions: tuple[str, ...]
    config_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolMetadata:
    """Aggregated metadata describing a tool definition."""

    schema_version: str
    identity: ToolIdentity
    behaviour: ToolBehaviour
    ordering: ToolOrdering
    files: ToolFiles


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Immutable representation of a tool catalog entry."""

    metadata: ToolMetadata
    runtime: RuntimeDefinition | None
    diagnostics_bundle: DiagnosticsBundle
    documentation: DocumentationBundle | None
    options: tuple[OptionDefinition, ...]
    actions: tuple[ActionDefinition, ...]
    source: Path

    @property
    def schema_version(self) -> str:
        """Return the schema version associated with this tool definition."""
        return self.metadata.schema_version

    @property
    def name(self) -> str:
        """Return the primary identifier of the catalog tool."""
        return self.metadata.identity.name

    @property
    def aliases(self) -> tuple[str, ...]:
        """Return alternate names referencing the tool."""
        return self.metadata.identity.aliases

    @property
    def description(self) -> str:
        """Return the human-readable description of the tool."""
        return self.metadata.identity.description

    @property
    def languages(self) -> tuple[str, ...]:
        """Return languages targeted by the tool's actions."""
        return self.metadata.identity.languages

    @property
    def tags(self) -> tuple[str, ...]:
        """Return tag metadata associated with the tool definition."""
        return self.metadata.identity.tags

    @property
    def default_enabled(self) -> bool:
        """Return ``True`` when the tool should be enabled by default."""
        return self.metadata.behaviour.default_enabled

    @property
    def auto_install(self) -> bool:
        """Return ``True`` when the tool supports automatic runtime installation."""
        return self.metadata.behaviour.auto_install

    @property
    def phase(self) -> str:
        """Return the execution phase in which the tool participates."""
        return self.metadata.ordering.phase

    @property
    def before(self) -> tuple[str, ...]:
        """Return tool identifiers that should run before this tool."""
        return self.metadata.ordering.before

    @property
    def after(self) -> tuple[str, ...]:
        """Return tool identifiers that should run after this tool."""
        return self.metadata.ordering.after

    @property
    def file_extensions(self) -> tuple[str, ...]:
        """Return supported file extensions for the tool actions."""
        return self.metadata.files.file_extensions

    @property
    def config_files(self) -> tuple[str, ...]:
        """Return recognized configuration files for the tool."""
        return self.metadata.files.config_files

    @staticmethod
    def from_mapping(
        data: Mapping[str, JSONValue],
        *,
        source: Path,
        catalog_root: Path,
    ) -> ToolDefinition:
        """Create a ``ToolDefinition`` from JSON data.

        Args:
            data: Mapping containing tool configuration.
            source: Filesystem path to the JSON document providing the data.
            catalog_root: Root directory containing catalog documents and documentation.

        Returns:
            ToolDefinition: Frozen tool definition materialised from the mapping.

        Raises:
            CatalogIntegrityError: If the schema version or required fields are invalid.

        """

        context = str(source)
        schema_version_value = expect_string(
            data.get("schemaVersion"),
            key="schemaVersion",
            context=context,
        )
        if schema_version_value != TOOL_SCHEMA_VERSION:
            raise CatalogIntegrityError(
                f"{context}: schemaVersion '{schema_version_value}' is not supported;"
                f" expected '{TOOL_SCHEMA_VERSION}'",
            )

        metadata = parse_tool_metadata(
            data,
            context=context,
            schema_version=schema_version_value,
        )
        runtime_value = parse_runtime_definition(data, context=context)
        diagnostics_bundle = DiagnosticsBundle.from_tool_mapping(data, context=context)
        documentation_value = parse_documentation_bundle(
            data,
            context=context,
            catalog_root=catalog_root,
            source=source,
        )
        options_value = options_array(data.get("options"), key="options", context=context)
        actions_value = actions_array(data.get("actions"), key="actions", context=context)
        return ToolDefinition(
            metadata=metadata,
            runtime=runtime_value,
            diagnostics_bundle=diagnostics_bundle,
            documentation=documentation_value,
            options=options_value,
            actions=actions_value,
            source=source,
        )


def parse_tool_metadata(
    data: Mapping[str, JSONValue],
    *,
    context: str,
    schema_version: str,
) -> ToolMetadata:
    """Return :class:`ToolMetadata` parsed from the provided mapping.

    Args:
        data: Mapping describing tool metadata.
        context: Human-readable context used in error messages.
        schema_version: Schema version declared in the catalog entry.

    Returns:
        ToolMetadata: Aggregated metadata describing the tool entry.

    Raises:
        CatalogIntegrityError: If required metadata is missing or invalid.

    """

    identity = ToolIdentity(
        name=expect_string(data.get("name"), key="name", context=context),
        aliases=string_array(data.get("aliases"), key="aliases", context=context),
        description=expect_string(
            data.get("description"),
            key="description",
            context=context,
        ),
        languages=string_array(data.get("languages"), key="languages", context=context),
        tags=string_array(data.get("tags"), key="tags", context=context),
    )
    behaviour = ToolBehaviour(
        default_enabled=optional_bool(
            data.get("defaultEnabled"),
            key="defaultEnabled",
            context=context,
            default=True,
        ),
        auto_install=optional_bool(
            data.get("autoInstall"),
            key="autoInstall",
            context=context,
            default=False,
        ),
    )
    ordering = ToolOrdering(
        phase=expect_string(data.get("phase"), key="phase", context=context),
        before=string_array(data.get("before"), key="before", context=context),
        after=string_array(data.get("after"), key="after", context=context),
    )
    files = ToolFiles(
        file_extensions=string_array(
            data.get("fileExtensions"),
            key="fileExtensions",
            context=context,
        ),
        config_files=string_array(
            data.get("configFiles"),
            key="configFiles",
            context=context,
        ),
    )
    return ToolMetadata(
        schema_version=schema_version,
        identity=identity,
        behaviour=behaviour,
        ordering=ordering,
        files=files,
    )


def parse_runtime_definition(
    data: Mapping[str, JSONValue],
    *,
    context: str,
) -> RuntimeDefinition | None:
    """Return a runtime definition if present in *data*.

    Args:
        data: Mapping describing tool metadata.
        context: Human-readable context used in error messages.

    Returns:
        RuntimeDefinition | None: Parsed runtime definition or ``None`` when absent.

    Raises:
        CatalogIntegrityError: If the runtime mapping is present but invalid.

    """

    runtime_data = data.get("runtime")
    if not isinstance(runtime_data, Mapping):
        return None
    mapping = expect_mapping(runtime_data, key="runtime", context=context)
    return RuntimeDefinition.from_mapping(mapping, context=f"{context}.runtime")


def parse_documentation_bundle(
    data: Mapping[str, JSONValue],
    *,
    context: str,
    catalog_root: Path,
    source: Path,
) -> DocumentationBundle | None:
    """Return documentation bundle metadata if present in *data*.

    Args:
        data: Mapping describing tool metadata.
        context: Human-readable context used in error messages.
        catalog_root: Root directory containing catalog documentation.
        source: Path to the JSON file currently being processed.

    Returns:
        DocumentationBundle | None: Parsed documentation bundle or ``None`` when absent.

    Raises:
        CatalogIntegrityError: If the documentation mapping is present but invalid.

    """

    documentation_data = data.get("documentation")
    if not isinstance(documentation_data, Mapping):
        return None
    mapping = expect_mapping(documentation_data, key="documentation", context=context)
    return DocumentationBundle.from_mapping(
        mapping,
        context=f"{context}.documentation",
        catalog_root=catalog_root,
        source=source,
    )


TOOL_MODEL_EXPORTS: Final[tuple[str, ...]] = (
    "ToolBehaviour",
    "ToolDefinition",
    "ToolFiles",
    "ToolIdentity",
    "ToolMetadata",
    "ToolOrdering",
    "parse_documentation_bundle",
    "parse_runtime_definition",
    "parse_tool_metadata",
)

TOOL_MODEL_OBJECTS: Final[tuple[object, ...]] = (
    ToolBehaviour,
    ToolDefinition,
    ToolFiles,
    ToolIdentity,
    ToolMetadata,
    ToolOrdering,
    parse_documentation_bundle,
    parse_runtime_definition,
    parse_tool_metadata,
)
