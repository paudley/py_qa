"""Catalog data structures and helpers used by the loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping, Sequence, TypeAlias, cast

from .errors import CatalogIntegrityError
from .types import STRATEGY_SCHEMA_VERSION, TOOL_SCHEMA_VERSION, JSONValue
from .utils import (
    expect_mapping,
    expect_string,
    freeze_json_mapping,
    optional_bool,
    optional_number,
    optional_string,
    string_array,
    string_mapping,
)


@dataclass(frozen=True, slots=True)
class StrategyReference:
    """Reference to a reusable strategy defined in the strategy catalog."""

    strategy: str
    config: Mapping[str, JSONValue]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "StrategyReference":
        """Create a ``StrategyReference`` instance from JSON data.

        Args:
            data: Mapping that describes the strategy reference.
            context: Human readable context used in error messages.

        Returns:
            StrategyReference: Frozen representation of the strategy reference.

        Raises:
            CatalogIntegrityError: If required keys are missing or invalid.
        """

        strategy_value = expect_string(data.get("strategy"), key="strategy", context=context)
        config_data = data.get("config")
        config_mapping = (
            freeze_json_mapping(cast(Mapping[str, JSONValue], config_data), context=f"{context}.config")
            if isinstance(config_data, Mapping)
            else MappingProxyType({})
        )
        return StrategyReference(strategy=strategy_value, config=config_mapping)


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    """Strategy-backed command definition bound to a tool action."""

    reference: StrategyReference

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "CommandDefinition":
        """Create a ``CommandDefinition`` from JSON data.

        Args:
            data: Mapping containing command configuration.
            context: Human readable context used in error messages.

        Returns:
            CommandDefinition: Frozen command definition.
        """

        return CommandDefinition(reference=StrategyReference.from_mapping(data, context=context))


@dataclass(frozen=True, slots=True)
class ParserDefinition:
    """Strategy-backed parser definition bound to a tool action."""

    reference: StrategyReference

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "ParserDefinition":
        """Create a ``ParserDefinition`` from JSON data.

        Args:
            data: Mapping containing parser configuration.
            context: Human readable context used in error messages.

        Returns:
            ParserDefinition: Frozen parser definition.
        """

        return ParserDefinition(reference=StrategyReference.from_mapping(data, context=context))


@dataclass(frozen=True, slots=True)
class RuntimeInstallDefinition:
    """Declarative installation strategy for tool runtimes."""

    strategy: str
    config: Mapping[str, JSONValue]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "RuntimeInstallDefinition":
        """Create an install definition from JSON data.

        Args:
            data: Mapping containing installation configuration.
            context: Human readable context used in error messages.

        Returns:
            RuntimeInstallDefinition: Frozen installation definition.

        Raises:
            CatalogIntegrityError: If the strategy identifier is missing or invalid.
        """

        strategy_value = expect_string(data.get("strategy"), key="strategy", context=context)
        config_data = data.get("config")
        config_mapping = (
            freeze_json_mapping(cast(Mapping[str, JSONValue], config_data), context=f"{context}.config")
            if isinstance(config_data, Mapping)
            else MappingProxyType({})
        )
        return RuntimeInstallDefinition(strategy=strategy_value, config=config_mapping)


RuntimeType: TypeAlias = Literal["python", "npm", "binary", "go", "lua", "perl", "rust"]


@dataclass(frozen=True, slots=True)
class RuntimeDefinition:
    """Runtime metadata required to execute a tool."""

    kind: RuntimeType
    package: str | None
    min_version: str | None
    max_version: str | None
    version_command: tuple[str, ...]
    binaries: Mapping[str, str]
    install: RuntimeInstallDefinition | None

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "RuntimeDefinition":
        """Create a ``RuntimeDefinition`` from JSON data.

        Args:
            data: Mapping containing runtime configuration.
            context: Human readable context used in error messages.

        Returns:
            RuntimeDefinition: Frozen runtime metadata.

        Raises:
            CatalogIntegrityError: If any required runtime fields are missing or invalid.
        """

        kind_value = expect_string(data.get("type"), key="type", context=context)
        package_value = optional_string(data.get("package"), key="package", context=context)
        min_version_value = optional_string(data.get("minVersion"), key="minVersion", context=context)
        max_version_value = optional_string(data.get("maxVersion"), key="maxVersion", context=context)
        version_command_value = string_array(data.get("versionCommand"), key="versionCommand", context=context)
        binaries_value = string_mapping(data.get("binaries"), key="binaries", context=context)
        install_data = data.get("install")
        install_value = (
            RuntimeInstallDefinition.from_mapping(
                cast(Mapping[str, JSONValue], install_data), context=f"{context}.install"
            )
            if isinstance(install_data, Mapping)
            else None
        )
        return RuntimeDefinition(
            kind=cast(RuntimeType, kind_value),
            package=package_value,
            min_version=min_version_value,
            max_version=max_version_value,
            version_command=version_command_value,
            binaries=binaries_value,
            install=install_value,
        )


@dataclass(frozen=True, slots=True)
class DiagnosticsDefinition:
    """Diagnostic post-processing configuration."""

    dedupe: Mapping[str, str]
    severity_mapping: Mapping[str, str]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "DiagnosticsDefinition":
        """Create a ``DiagnosticsDefinition`` from JSON data.

        Args:
            data: Mapping containing diagnostics metadata.
            context: Human readable context used in error messages.

        Returns:
            DiagnosticsDefinition: Frozen diagnostics configuration.
        """

        dedupe_value = string_mapping(data.get("dedupe"), key="dedupe", context=context)
        severity_value = string_mapping(data.get("severityMapping"), key="severityMapping", context=context)
        return DiagnosticsDefinition(dedupe=dedupe_value, severity_mapping=severity_value)


@dataclass(frozen=True, slots=True)
class SuppressionsDefinition:
    """Suppressions applied to diagnostics emitted by a tool."""

    tests: tuple[str, ...]
    general: tuple[str, ...]
    duplicates: tuple[str, ...]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "SuppressionsDefinition":
        """Create a ``SuppressionsDefinition`` from JSON data.

        Args:
            data: Mapping containing suppression settings.
            context: Human readable context used in error messages.

        Returns:
            SuppressionsDefinition: Frozen suppression configuration.
        """

        tests_value = string_array(data.get("tests"), key="tests", context=context)
        general_value = string_array(data.get("general"), key="general", context=context)
        duplicates_value = string_array(data.get("duplicates"), key="duplicates", context=context)
        return SuppressionsDefinition(
            tests=tests_value,
            general=general_value,
            duplicates=duplicates_value,
        )


OptionType: TypeAlias = Literal[
    "string",
    "str",
    "boolean",
    "bool",
    "integer",
    "int",
    "number",
    "float",
    "array",
    "object",
    "path",
    "list[str]",
]


@dataclass(frozen=True, slots=True)
class CliOptionMetadata:
    """CLI representation details for catalog options."""

    flag: str | None
    short_flag: str | None
    multiple: bool

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "CliOptionMetadata":
        """Create CLI metadata from JSON data.

        Args:
            data: Mapping containing CLI option metadata.
            context: Human readable context used in error messages.

        Returns:
            CliOptionMetadata: Frozen CLI metadata configuration.
        """

        flag_value = optional_string(data.get("flag"), key="flag", context=context)
        short_flag_value = optional_string(data.get("shortFlag"), key="shortFlag", context=context)
        multiple_value = optional_bool(data.get("multiple"), key="multiple", context=context, default=False)
        return CliOptionMetadata(flag=flag_value, short_flag=short_flag_value, multiple=multiple_value)


@dataclass(frozen=True, slots=True)
class OptionDefinition:
    """Declarative tool option exposed to configuration surfaces."""

    name: str
    option_type: OptionType
    description: str | None
    default: JSONValue
    cli: CliOptionMetadata | None
    choices: tuple[str, ...]
    aliases: tuple[str, ...]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "OptionDefinition":
        """Create an ``OptionDefinition`` from JSON data.

        Args:
            data: Mapping containing option configuration.
            context: Human readable context used in error messages.

        Returns:
            OptionDefinition: Frozen option definition.

        Raises:
            CatalogIntegrityError: If required option fields are missing or invalid.
        """

        name_value = expect_string(data.get("name"), key="name", context=context)
        option_type_value = expect_string(data.get("type"), key="type", context=context)
        description_value = optional_string(data.get("description"), key="description", context=context)
        default_value = data.get("default")
        cli_data = data.get("cli")
        cli_value = (
            CliOptionMetadata.from_mapping(cast(Mapping[str, JSONValue], cli_data), context=f"{context}.cli")
            if isinstance(cli_data, Mapping)
            else None
        )
        choices_value = string_array(data.get("choices"), key="choices", context=context)
        aliases_value = string_array(data.get("aliases"), key="aliases", context=context)
        return OptionDefinition(
            name=name_value,
            option_type=cast(OptionType, option_type_value),
            description=description_value,
            default=default_value,
            cli=cli_value,
            choices=choices_value,
            aliases=aliases_value,
        )


@dataclass(frozen=True, slots=True)
class OptionGroupDefinition:
    """Grouped options for documentation purposes."""

    title: str
    options: tuple[OptionDefinition, ...]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "OptionGroupDefinition":
        title_value = expect_string(data.get("title"), key="title", context=context)
        options_value = _options_array(data.get("options"), key="options", context=context)
        return OptionGroupDefinition(title=title_value, options=options_value)


@dataclass(frozen=True, slots=True)
class OptionDocumentationBundle:
    """Documentation helpers for describing tool options."""

    groups: tuple[OptionGroupDefinition, ...]
    entries: tuple[OptionDefinition, ...]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "OptionDocumentationBundle":
        groups_data = data.get("groups")
        groups_value: tuple[OptionGroupDefinition, ...] = ()
        if isinstance(groups_data, Sequence) and not isinstance(groups_data, (str, bytes, bytearray)):
            group_items: list[OptionGroupDefinition] = []
            for index, element in enumerate(groups_data):
                element_mapping = expect_mapping(element, key=f"groups[{index}]", context=context)
                group_items.append(
                    OptionGroupDefinition.from_mapping(
                        element_mapping,
                        context=f"{context}.groups[{index}]",
                    )
                )
            groups_value = tuple(group_items)
        entries_value = _options_array(data.get("entries"), key="entries", context=context)
        return OptionDocumentationBundle(groups=groups_value, entries=entries_value)


@dataclass(frozen=True, slots=True)
class DocumentationEntry:
    """Documentation resource resolved from catalog metadata."""

    format: str
    content: str

    @staticmethod
    def from_mapping(
        data: Mapping[str, JSONValue],
        *,
        context: str,
        catalog_root: Path,
        source: Path,
    ) -> "DocumentationEntry":
        """Create documentation entry metadata from JSON data."""

        format_value = optional_string(data.get("format"), key="format", context=context) or "text"
        text_value = data.get("text")
        if isinstance(text_value, str):
            return DocumentationEntry(format=format_value, content=text_value)
        path_value = data.get("path")
        if isinstance(path_value, str):
            doc_path = Path(path_value)
            if not doc_path.is_absolute():
                doc_path = (catalog_root / path_value).resolve()
                if not doc_path.exists():
                    doc_path = (source.parent / path_value).resolve()
            if not doc_path.is_file():
                raise CatalogIntegrityError(f"{context}: documentation path '{path_value}' not found")
            try:
                content = doc_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise CatalogIntegrityError(f"{context}: unable to read documentation '{doc_path}'") from exc
            return DocumentationEntry(format=format_value, content=content)
        raise CatalogIntegrityError(f"{context}: documentation entry must define either 'text' or 'path'")


@dataclass(frozen=True, slots=True)
class DocumentationBundle:
    """Grouped documentation resources for a tool."""

    help: DocumentationEntry | None
    command: DocumentationEntry | None
    shared: DocumentationEntry | None

    @staticmethod
    def from_mapping(
        data: Mapping[str, JSONValue],
        *,
        context: str,
        catalog_root: Path,
        source: Path,
    ) -> "DocumentationBundle":
        """Create a ``DocumentationBundle`` from JSON data."""

        help_entry = _documentation_entry(
            data.get("help"),
            context=f"{context}.help",
            catalog_root=catalog_root,
            source=source,
        )
        command_entry = _documentation_entry(
            data.get("commandHelp"),
            context=f"{context}.commandHelp",
            catalog_root=catalog_root,
            source=source,
        )
        shared_entry = _documentation_entry(
            data.get("shared"),
            context=f"{context}.shared",
            catalog_root=catalog_root,
            source=source,
        )
        if help_entry is None and command_entry is None and shared_entry is None:
            raise CatalogIntegrityError(f"{context}: documentation block must include at least one entry")
        return DocumentationBundle(help=help_entry, command=command_entry, shared=shared_entry)


def _documentation_entry(
    value: JSONValue | None,
    *,
    context: str,
    catalog_root: Path,
    source: Path,
) -> DocumentationEntry | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise CatalogIntegrityError(f"{context}: documentation entry must be an object")
    return DocumentationEntry.from_mapping(
        cast(Mapping[str, JSONValue], value),
        context=context,
        catalog_root=catalog_root,
        source=source,
    )


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    """Executable action backed by strategies."""

    name: str
    description: str | None
    append_files: bool
    is_fix: bool
    ignore_exit: bool
    timeout_seconds: float | None
    env: Mapping[str, str]
    filters: tuple[str, ...]
    command: CommandDefinition
    parser: ParserDefinition | None

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "ActionDefinition":
        """Create an ``ActionDefinition`` from JSON data.

        Args:
            data: Mapping containing action configuration.
            context: Human readable context used in error messages.

        Returns:
            ActionDefinition: Frozen action definition.

        Raises:
            CatalogIntegrityError: If required action fields are missing or invalid.
        """

        name_value = expect_string(data.get("name"), key="name", context=context)
        description_value = optional_string(data.get("description"), key="description", context=context)
        append_files_value = optional_bool(data.get("appendFiles"), key="appendFiles", context=context, default=True)
        is_fix_value = optional_bool(data.get("isFix"), key="isFix", context=context, default=False)
        ignore_exit_value = optional_bool(data.get("ignoreExit"), key="ignoreExit", context=context, default=False)
        timeout_value = optional_number(data.get("timeoutSeconds"), key="timeoutSeconds", context=context)
        env_value = string_mapping(data.get("env"), key="env", context=context)
        filters_value = string_array(data.get("filters"), key="filters", context=context)
        command_data = expect_mapping(data.get("command"), key="command", context=context)
        command_value = CommandDefinition.from_mapping(command_data, context=f"{context}.command")
        parser_data = data.get("parser")
        parser_value = (
            ParserDefinition.from_mapping(cast(Mapping[str, JSONValue], parser_data), context=f"{context}.parser")
            if isinstance(parser_data, Mapping)
            else None
        )
        return ActionDefinition(
            name=name_value,
            description=description_value,
            append_files=append_files_value,
            is_fix=is_fix_value,
            ignore_exit=ignore_exit_value,
            timeout_seconds=timeout_value,
            env=env_value,
            filters=filters_value,
            command=command_value,
            parser=parser_value,
        )


@dataclass(frozen=True, slots=True)
class DiagnosticsBundle:
    """Container for diagnostics and suppression metadata."""

    diagnostics: DiagnosticsDefinition | None
    suppressions: SuppressionsDefinition | None


@dataclass(frozen=True, slots=True)
class CatalogFragment:
    """Shared catalog fragment intended for reuse across tool definitions."""

    name: str
    data: Mapping[str, JSONValue]
    source: Path


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    """Materialized catalog data paired with a deterministic checksum."""

    tools: tuple[ToolDefinition, ...]
    strategies: tuple[StrategyDefinition, ...]
    fragments: tuple[CatalogFragment, ...]
    checksum: str


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Immutable representation of a tool catalog entry."""

    schema_version: str
    name: str
    aliases: tuple[str, ...]
    description: str
    languages: tuple[str, ...]
    tags: tuple[str, ...]
    default_enabled: bool
    auto_install: bool
    phase: str
    before: tuple[str, ...]
    after: tuple[str, ...]
    file_extensions: tuple[str, ...]
    config_files: tuple[str, ...]
    runtime: RuntimeDefinition | None
    diagnostics_bundle: DiagnosticsBundle
    documentation: DocumentationBundle | None
    options: tuple[OptionDefinition, ...]
    actions: tuple[ActionDefinition, ...]
    source: Path

    @staticmethod
    def from_mapping(
        data: Mapping[str, JSONValue],
        *,
        source: Path,
        catalog_root: Path,
    ) -> "ToolDefinition":
        """Create a ``ToolDefinition`` from JSON data.

        Args:
            data: Mapping containing tool configuration.
            source: Filesystem path to the JSON document providing the data.

        Returns:
            ToolDefinition: Frozen tool definition materialized from the mapping.

        Raises:
            CatalogIntegrityError: If the schema version or required fields are invalid.
        """

        context = str(source)
        schema_version_value = expect_string(data.get("schemaVersion"), key="schemaVersion", context=context)
        if schema_version_value != TOOL_SCHEMA_VERSION:
            raise CatalogIntegrityError(
                f"{context}: schemaVersion '{schema_version_value}' is not supported; expected '{TOOL_SCHEMA_VERSION}'"
            )
        name_value = expect_string(data.get("name"), key="name", context=context)
        aliases_value = string_array(data.get("aliases"), key="aliases", context=context)
        description_value = expect_string(data.get("description"), key="description", context=context)
        languages_value = string_array(data.get("languages"), key="languages", context=context)
        tags_value = string_array(data.get("tags"), key="tags", context=context)
        default_enabled_value = optional_bool(
            data.get("defaultEnabled"), key="defaultEnabled", context=context, default=True
        )
        auto_install_value = optional_bool(data.get("autoInstall"), key="autoInstall", context=context, default=False)
        phase_value = expect_string(data.get("phase"), key="phase", context=context)
        before_value = string_array(data.get("before"), key="before", context=context)
        after_value = string_array(data.get("after"), key="after", context=context)
        file_extensions_value = string_array(data.get("fileExtensions"), key="fileExtensions", context=context)
        config_files_value = string_array(data.get("configFiles"), key="configFiles", context=context)
        runtime_data = data.get("runtime")
        runtime_value = (
            RuntimeDefinition.from_mapping(cast(Mapping[str, JSONValue], runtime_data), context=f"{context}.runtime")
            if isinstance(runtime_data, Mapping)
            else None
        )
        diagnostics_data = data.get("diagnostics")
        diagnostics_value = (
            DiagnosticsDefinition.from_mapping(
                cast(Mapping[str, JSONValue], diagnostics_data), context=f"{context}.diagnostics"
            )
            if isinstance(diagnostics_data, Mapping)
            else None
        )
        suppressions_data = data.get("suppressions")
        suppressions_value = (
            SuppressionsDefinition.from_mapping(
                cast(Mapping[str, JSONValue], suppressions_data), context=f"{context}.suppressions"
            )
            if isinstance(suppressions_data, Mapping)
            else None
        )
        documentation_data = data.get("documentation")
        documentation_value = (
            DocumentationBundle.from_mapping(
                cast(Mapping[str, JSONValue], documentation_data),
                context=f"{context}.documentation",
                catalog_root=catalog_root,
                source=source,
            )
            if isinstance(documentation_data, Mapping)
            else None
        )
        options_value = _options_array(data.get("options"), key="options", context=context)
        actions_value = _actions_array(data.get("actions"), key="actions", context=context)
        diagnostics_bundle = DiagnosticsBundle(diagnostics=diagnostics_value, suppressions=suppressions_value)
        return ToolDefinition(
            schema_version=schema_version_value,
            name=name_value,
            aliases=aliases_value,
            description=description_value,
            languages=languages_value,
            tags=tags_value,
            default_enabled=default_enabled_value,
            auto_install=auto_install_value,
            phase=phase_value,
            before=before_value,
            after=after_value,
            file_extensions=file_extensions_value,
            config_files=config_files_value,
            runtime=runtime_value,
            diagnostics_bundle=diagnostics_bundle,
            documentation=documentation_value,
            options=options_value,
            actions=actions_value,
            source=source,
        )


StrategyType: TypeAlias = Literal["command", "parser", "formatter", "postProcessor", "installer"]


@dataclass(frozen=True, slots=True)
class StrategyConfigField:
    """Metadata describing a configuration field consumed by a strategy."""

    value_type: OptionType
    required: bool
    description: str | None

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> "StrategyConfigField":
        """Create a configuration field descriptor from JSON data.

        Args:
            data: Mapping describing an individual configuration field.
            context: Human readable context used in error messages.

        Returns:
            StrategyConfigField: Frozen descriptor for the configuration field.

        Raises:
            CatalogIntegrityError: If required field metadata is missing or invalid.
        """

        type_value = expect_string(data.get("type"), key="type", context=context)
        required_value = optional_bool(data.get("required"), key="required", context=context, default=False)
        description_value = optional_string(data.get("description"), key="description", context=context)
        return StrategyConfigField(
            value_type=cast(OptionType, type_value),
            required=required_value,
            description=description_value,
        )


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    """Immutable representation of a strategy catalog entry."""

    schema_version: str
    identifier: str
    strategy_type: StrategyType
    description: str | None
    implementation: str
    entry: str | None
    config: Mapping[str, StrategyConfigField]
    source: Path

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, source: Path) -> "StrategyDefinition":
        """Create a ``StrategyDefinition`` from JSON data.

        Args:
            data: Mapping containing strategy configuration.
            source: Filesystem path to the JSON document providing the data.

        Returns:
            StrategyDefinition: Frozen strategy definition materialized from the mapping.

        Raises:
            CatalogIntegrityError: If the schema version or required fields are invalid.
        """

        context = str(source)
        schema_version_value = expect_string(data.get("schemaVersion"), key="schemaVersion", context=context)
        if schema_version_value != STRATEGY_SCHEMA_VERSION:
            raise CatalogIntegrityError(
                f"{context}: schemaVersion '{schema_version_value}' is not supported; expected '{STRATEGY_SCHEMA_VERSION}'"
            )
        identifier_value = expect_string(data.get("id"), key="id", context=context)
        strategy_type_value = expect_string(data.get("type"), key="type", context=context)
        description_value = optional_string(data.get("description"), key="description", context=context)
        implementation_value = expect_string(data.get("implementation"), key="implementation", context=context)
        entry_value = optional_string(data.get("entry"), key="entry", context=context)
        config_data = data.get("config")
        config_value = _strategy_config_mapping(config_data, context=f"{context}.config")
        return StrategyDefinition(
            schema_version=schema_version_value,
            identifier=identifier_value,
            strategy_type=cast(StrategyType, strategy_type_value),
            description=description_value,
            implementation=implementation_value,
            entry=entry_value,
            config=config_value,
            source=source,
        )


def _options_array(value: JSONValue | None, *, key: str, context: str) -> tuple[OptionDefinition, ...]:
    """Return a tuple of option definitions."""

    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be an array of option objects")
    options: list[OptionDefinition] = []
    for index, element in enumerate(value):
        element_mapping = expect_mapping(element, key=f"{key}[{index}]", context=context)
        options.append(
            OptionDefinition.from_mapping(
                element_mapping,
                context=f"{context}.{key}[{index}]",
            )
        )
    return tuple(options)


def _actions_array(value: JSONValue | None, *, key: str, context: str) -> tuple[ActionDefinition, ...]:
    """Return a tuple of action definitions."""

    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CatalogIntegrityError(f"{context}: expected '{key}' to be an array of action objects")
    actions: list[ActionDefinition] = []
    for index, element in enumerate(value):
        element_mapping = expect_mapping(element, key=f"{key}[{index}]", context=context)
        actions.append(
            ActionDefinition.from_mapping(
                element_mapping,
                context=f"{context}.{key}[{index}]",
            )
        )
    if not actions:
        raise CatalogIntegrityError(f"{context}: '{key}' must contain at least one action")
    return tuple(actions)


def _strategy_config_mapping(value: JSONValue | None, *, context: str) -> Mapping[str, StrategyConfigField]:
    """Return an immutable mapping of strategy configuration descriptors."""

    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise CatalogIntegrityError(f"{context}: expected strategy config to be an object")
    frozen: dict[str, StrategyConfigField] = {}
    for field_name, field_value in value.items():
        if not isinstance(field_name, str):
            raise CatalogIntegrityError(f"{context}: expected strategy config keys to be strings")
        field_mapping = expect_mapping(field_value, key=field_name, context=context)
        frozen[field_name] = StrategyConfigField.from_mapping(
            field_mapping,
            context=f"{context}.{field_name}",
        )
    return MappingProxyType(frozen)


__all__ = [
    "ActionDefinition",
    "CatalogFragment",
    "CatalogSnapshot",
    "CommandDefinition",
    "DiagnosticsBundle",
    "DiagnosticsDefinition",
    "DocumentationBundle",
    "DocumentationEntry",
    "OptionDefinition",
    "OptionDocumentationBundle",
    "OptionGroupDefinition",
    "ParserDefinition",
    "RuntimeDefinition",
    "RuntimeInstallDefinition",
    "StrategyConfigField",
    "StrategyDefinition",
    "StrategyReference",
    "StrategyType",
    "SuppressionsDefinition",
    "ToolDefinition",
]
