# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Registry wiring for built-in and catalog-driven tool definitions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeAlias

from pyqa.platform.paths import get_pyqa_root
from tooling_spec.catalog.model_actions import ActionDefinition
from tooling_spec.catalog.types import JSONValue

from ..catalog.errors import CatalogIntegrityError
from ..catalog.loader import ToolCatalogLoader
from ..catalog.model_catalog import CatalogSnapshot
from ..catalog.model_diagnostics import SuppressionsDefinition
from ..catalog.model_documentation import DocumentationBundle, DocumentationEntry
from ..catalog.model_references import StrategyReference
from ..catalog.model_runtime import SUPPORTED_RUNTIME_TYPES, RuntimeInstallDefinition, RuntimeType
from ..catalog.model_strategy import StrategyCallable, StrategyDefinition
from ..catalog.model_tool import ToolDefinition
from .base import (
    CommandBuilder,
    DeferredCommand,
    InstallerCallable,
    Parser,
    PhaseLiteral,
    Tool,
    ToolAction,
    ToolDocumentation,
    ToolDocumentationEntry,
)
from .builtin_helpers import (
    CARGO_AVAILABLE,
    CPANM_AVAILABLE,
    LUA_AVAILABLE,
    LUAROCKS_AVAILABLE,
)
from .registry import DEFAULT_REGISTRY, ToolRegistry

ToolRuntimeKind = Literal["python", "npm", "binary", "go", "lua", "perl", "rust"]
DEFAULT_RUNTIME_KIND: Final[ToolRuntimeKind] = "python"
COMMAND_STRATEGY: Final[str] = "command"
PARSER_STRATEGY: Final[str] = "parser"
INSTALLER_STRATEGY: Final[str] = "installer"

RUNTIME_LITERAL_MAP: Final[dict[str, ToolRuntimeKind]] = {name: name for name in SUPPORTED_RUNTIME_TYPES}
PHASE_LITERAL_MAP: Final[dict[str, PhaseLiteral]] = {
    "format": "format",
    "lint": "lint",
    "analysis": "analysis",
    "security": "security",
    "test": "test",
    "coverage": "coverage",
    "utility": "utility",
}


@dataclass(frozen=True)
class _CatalogCacheEntry:
    """Cached catalog payload containing the snapshot and materialised tools."""

    checksum: str
    snapshot: CatalogSnapshot
    tools: tuple[Tool, ...]


_CATALOG_CACHE: dict[tuple[Path, Path], _CatalogCacheEntry] = {}


StrategyResult: TypeAlias = (
    CommandBuilder | Parser | InstallerCallable | Sequence[str] | Mapping[str, JSONValue] | JSONValue | None
)


@dataclass(frozen=True)
class _RuntimeConfig:
    """Normalised runtime metadata extracted from catalog definitions."""

    kind: ToolRuntimeKind
    package: str | None
    min_version: str | None
    version_command: tuple[str, ...] | None
    installers: tuple[InstallerCallable, ...]


def register_catalog_tools(
    registry: ToolRegistry | None = None,
    *,
    catalog_root: Path | None = None,
    schema_root: Path | None = None,
) -> CatalogSnapshot:
    """Register catalog-backed tools with the provided *registry*."""
    target = registry if registry is not None else DEFAULT_REGISTRY
    loader = ToolCatalogLoader(
        catalog_root=_resolve_catalog_root(catalog_root),
        schema_root=schema_root,
    )
    cache_entry = _load_catalog_from_cache(loader)
    target.reset()
    for tool in cache_entry.tools:
        target.register(tool)
    if len(target) != len(cache_entry.snapshot.tools):
        raise CatalogIntegrityError("Failed to register catalog tools into registry")
    return cache_entry.snapshot


def initialize_registry(
    *,
    registry: ToolRegistry | None = None,
    catalog_root: Path | None = None,
    schema_root: Path | None = None,
) -> CatalogSnapshot:
    """Initialise *registry* from the catalog and return the resulting snapshot."""
    target = registry if registry is not None else DEFAULT_REGISTRY
    return register_catalog_tools(
        target,
        catalog_root=catalog_root,
        schema_root=schema_root,
    )


def _resolve_catalog_root(candidate: Path | None) -> Path:
    if candidate is not None:
        return candidate
    project_root = get_pyqa_root()
    catalog = project_root / "tooling" / "catalog"
    if not catalog.exists():
        raise FileNotFoundError("Unable to locate tooling/catalog directory")
    return catalog


def _materialize_tool(
    definition: ToolDefinition,
    strategies: Mapping[str, StrategyDefinition],
) -> Tool:
    runtime_config = _extract_runtime(definition, strategies)
    documentation_value = _convert_documentation(definition.components.documentation)
    suppressions_tuple = _extract_suppressions(definition.components.diagnostics_bundle.suppressions)
    actions = tuple(
        _materialize_action(action, strategies, context=f"{definition.name}:{action.name}")
        for action in definition.components.actions
    )

    tool = Tool(
        name=definition.name,
        actions=actions,
        phase=_normalize_phase_literal(definition.phase, context=definition.name),
        before=definition.before,
        after=definition.after,
        languages=definition.languages,
        file_extensions=definition.file_extensions,
        config_files=definition.config_files,
        description=definition.description or "",
        auto_install=definition.auto_install,
        default_enabled=definition.default_enabled,
        automatically_fix=definition.automatically_fix,
        runtime=runtime_config.kind,
        package=runtime_config.package,
        min_version=runtime_config.min_version,
        version_command=runtime_config.version_command,
        suppressions_tests=suppressions_tuple.tests,
        suppressions_general=suppressions_tuple.general,
        suppressions_duplicates=suppressions_tuple.duplicates,
        installers=runtime_config.installers,
        tags=getattr(definition, "tags", ()),
        documentation=documentation_value,
    )
    _apply_environment_tags(tool)
    return tool


def _apply_environment_tags(tool: Tool) -> None:
    if not tool.tags:
        return
    available_map = {
        "requires-cargo": CARGO_AVAILABLE,
        "requires-cpanm": CPANM_AVAILABLE,
        "requires-lua": LUA_AVAILABLE,
        "requires-luarocks": LUAROCKS_AVAILABLE,
    }
    enabled = tool.default_enabled
    for tag in tool.tags:
        available = available_map.get(tag)
        if available is None:
            continue
        if not available:
            enabled = False
    tool.default_enabled = enabled


def _materialize_action(
    action: ActionDefinition,
    strategies: Mapping[str, StrategyDefinition],
    *,
    context: str,
) -> ToolAction:
    """Return a materialised :class:`ToolAction` derived from catalog metadata.

    Args:
        action: Action definition describing the command, parser, and execution.
        strategies: Strategy definitions keyed by identifier.
        context: Human-readable context used for error messages.

    Returns:
        ToolAction: Fully initialised tool action ready for registration.

    Raises:
        CatalogIntegrityError: If the associated command or parser strategies are invalid.
    """

    command_builder = _instantiate_command(action.command.reference, strategies, context=context)
    parser_instance = None
    if action.parser is not None:
        parser_instance = _instantiate_parser(action.parser.reference, strategies, context=context)

    env_mapping = {key: value for key, value in action.execution.env.items()}
    description = action.description or ""
    filters = action.execution.filters

    return ToolAction(
        name=action.name,
        command=command_builder,
        is_fix=action.execution.is_fix,
        append_files=action.execution.append_files,
        filter_patterns=filters,
        ignore_exit=action.execution.ignore_exit,
        description=description,
        timeout_s=action.execution.timeout_seconds,
        env=env_mapping,
        parser=parser_instance,
    )


def _instantiate_command(
    reference: StrategyReference,
    strategies: Mapping[str, StrategyDefinition],
    *,
    context: str,
) -> CommandBuilder:
    """Return a command builder resolved from ``reference``.

    Args:
        reference: Strategy reference describing the command implementation.
        strategies: Registry of available strategy definitions.
        context: Human-readable context used for error messages.

    Returns:
        CommandBuilder: Builder instance used to derive command arguments.

    Raises:
        CatalogIntegrityError: If the strategy is missing or returns unexpected data.
    """

    strategy_definition = strategies.get(reference.strategy)
    if strategy_definition is None:
        raise CatalogIntegrityError(f"{context}: unknown command strategy '{reference.strategy}'")
    if strategy_definition.strategy_type != COMMAND_STRATEGY:
        raise CatalogIntegrityError(
            f"{context}: strategy '{reference.strategy}' is not a command strategy",
        )
    factory = _resolve_strategy_callable(strategy_definition)
    config = _materialize_strategy_config(reference.config)
    instance = _call_strategy_factory(factory, config)
    return _ensure_command_builder(instance, context=context)


def _instantiate_parser(
    reference: StrategyReference,
    strategies: Mapping[str, StrategyDefinition],
    *,
    context: str,
) -> Parser:
    """Return a parser instance resolved from ``reference``.

    Args:
        reference: Strategy reference describing the parser implementation.
        strategies: Registry of available strategy definitions.
        context: Human-readable context used for error messages.

    Returns:
        Parser: Parser implementation aligned with :class:`ToolAction`.

    Raises:
        CatalogIntegrityError: If the strategy is missing or does not return a parser.
    """

    strategy_definition = strategies.get(reference.strategy)
    if strategy_definition is None:
        raise CatalogIntegrityError(f"{context}: unknown parser strategy '{reference.strategy}'")
    if strategy_definition.strategy_type != PARSER_STRATEGY:
        raise CatalogIntegrityError(
            f"{context}: strategy '{reference.strategy}' is not a parser strategy",
        )
    factory = _resolve_strategy_callable(strategy_definition)
    config = _materialize_strategy_config(reference.config)
    parser_candidate = _call_strategy_factory(factory, config)
    if not isinstance(parser_candidate, Parser):
        raise CatalogIntegrityError(f"{context}: parser strategy did not return a parser instance")
    return parser_candidate


def _instantiate_installer(
    reference: RuntimeInstallDefinition,
    strategies: Mapping[str, StrategyDefinition],
    *,
    context: str,
) -> InstallerCallable:
    """Return an installer callable resolved from ``reference``.

    Args:
        reference: Strategy reference describing the installer implementation.
        strategies: Registry of available strategy definitions.
        context: Human-readable context used for error messages.

    Returns:
        InstallerCallable: Callable invoked to provision runtime dependencies.

    Raises:
        CatalogIntegrityError: If the strategy is missing or does not return a callable.
    """

    strategy_definition = strategies.get(reference.strategy)
    if strategy_definition is None:
        raise CatalogIntegrityError(f"{context}: unknown installer strategy '{reference.strategy}'")
    if strategy_definition.strategy_type != INSTALLER_STRATEGY:
        raise CatalogIntegrityError(
            f"{context}: strategy '{reference.strategy}' is not an installer strategy",
        )
    factory = _resolve_strategy_callable(strategy_definition)
    raw_config = getattr(reference, "config", {})
    config = _materialize_strategy_config(raw_config)
    installer = _call_strategy_factory(factory, config)
    if not isinstance(installer, InstallerCallable):
        raise CatalogIntegrityError(
            f"{context}: installer strategy '{reference.strategy}' did not return a callable",
        )
    return installer


def _convert_documentation(bundle: DocumentationBundle | None) -> ToolDocumentation | None:
    if bundle is None:
        return None
    help_entry = _to_tool_doc_entry(bundle.help)
    command_entry = _to_tool_doc_entry(bundle.command)
    shared_entry = _to_tool_doc_entry(bundle.shared)
    if help_entry is None and command_entry is None and shared_entry is None:
        return None
    return ToolDocumentation(help=help_entry, command=command_entry, shared=shared_entry)


def _to_tool_doc_entry(entry: DocumentationEntry | None) -> ToolDocumentationEntry | None:
    if entry is None:
        return None
    if entry.content is None:
        return None
    return ToolDocumentationEntry(format=entry.format, content=entry.content)


def _resolve_strategy_callable(definition: StrategyDefinition) -> StrategyCallable:
    """Return the callable factory associated with ``definition``.

    Args:
        definition: Strategy definition sourced from the catalog snapshot.

    Returns:
        StrategyCallable: Factory callable that materialises strategy payloads.
    """

    return definition.build_factory()


def _call_strategy_factory(
    factory: StrategyCallable,
    config: Mapping[str, JSONValue],
) -> StrategyResult:
    """Invoke ``factory`` with ``config`` and return the resulting payload.

    Args:
        factory: Strategy callable resolved from catalog metadata.
        config: Normalised configuration mapping to pass to the strategy.

    Returns:
        StrategyResult: Payload produced by the strategy evaluation.
    """

    if config:
        return factory(config)
    return factory()


def _ensure_command_builder(instance: StrategyResult, *, context: str) -> CommandBuilder:
    """Return a validated command builder derived from ``instance``.

    Args:
        instance: Strategy payload describing or implementing a command.
        context: Human-readable context used for error messages.

    Returns:
        CommandBuilder: Builder object capable of constructing command arguments.

    Raises:
        CatalogIntegrityError: If ``instance`` cannot be converted into a builder.
    """

    if isinstance(instance, CommandBuilder):
        return instance
    if isinstance(instance, Sequence) and not isinstance(instance, (str, bytes, bytearray)):
        deferred = DeferredCommand(tuple(str(part) for part in instance))
        return deferred
    raise CatalogIntegrityError(
        f"{context}: command strategy did not return a valid command builder",
    )


def _materialize_strategy_config(raw: Mapping[str, JSONValue] | JSONValue) -> Mapping[str, JSONValue]:
    """Return a plain mapping of strategy configuration entries.

    Args:
        raw: Raw configuration payload sourced from catalog metadata.

    Returns:
        Mapping[str, JSONValue]: Mutable mapping suitable for strategy invocation.

    Raises:
        CatalogIntegrityError: If ``raw`` is neither a mapping nor ``None``.
    """

    if isinstance(raw, Mapping):
        return {str(key): _as_plain_json(value) for key, value in raw.items()}
    if raw is None:
        return {}
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        raise CatalogIntegrityError("Strategy configuration must be a mapping when provided")
    raise CatalogIntegrityError("Strategy configuration must be a mapping or null")


def _as_plain_json(value: JSONValue) -> JSONValue:
    """Return a JSON-compatible structure detached from catalog frozen types.

    Args:
        value: Raw JSON value drawn from catalog metadata.

    Returns:
        JSONValue: Copy of ``value`` with nested mappings converted to native containers.
    """

    if isinstance(value, Mapping):
        return {str(key): _as_plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_as_plain_json(item) for item in value]
    if isinstance(value, list):
        return [_as_plain_json(item) for item in value]
    return value


__all__ = [
    "clear_catalog_cache",
    "initialize_registry",
    "register_catalog_tools",
]


def clear_catalog_cache() -> None:
    """Clear the in-memory catalog snapshot cache used for tooling definitions.

    This helper exists primarily to support test isolation; production callers
    should not need to purge the cache explicitly.
    """
    _CATALOG_CACHE.clear()


def _load_catalog_from_cache(loader: ToolCatalogLoader) -> _CatalogCacheEntry:
    """Return a cached or freshly loaded catalog snapshot for *loader*.

    Args:
        loader: Loader responsible for reading the catalog and associated
            schemas from disk.

    Returns:
        _CatalogCacheEntry: Cached payload containing the catalog snapshot and
        materialised :class:`Tool` instances.

    """
    cache_key = _catalog_cache_key(loader.catalog_root, loader.schema_root)
    cached = _CATALOG_CACHE.get(cache_key)
    if cached is not None:
        current_checksum = loader.compute_checksum()
        if current_checksum == cached.checksum:
            return cached
    snapshot = loader.load_snapshot()
    strategies = {definition.identifier: definition for definition in snapshot.strategies}
    tools = tuple(_materialize_tool(definition, strategies) for definition in snapshot.tools)
    entry = _CatalogCacheEntry(checksum=snapshot.checksum, snapshot=snapshot, tools=tools)
    _CATALOG_CACHE[cache_key] = entry
    return entry


def _catalog_cache_key(catalog_root: Path, schema_root: Path | None) -> tuple[Path, Path]:
    """Return a canonical cache key for *catalog_root* and *schema_root*.

    Args:
        catalog_root: Path to the catalog directory.
        schema_root: Optional path to the schema directory; when ``None`` the
            directory adjacent to the catalog is used.

    Returns:
        tuple[Path, Path]: Tuple combining resolved catalog and schema paths.

    """
    resolved_catalog = catalog_root.resolve()
    schema_candidate = schema_root or (resolved_catalog.parent / "schema")
    resolved_schema = schema_candidate.resolve()
    return (resolved_catalog, resolved_schema)


@dataclass(frozen=True, slots=True)
class _SuppressionBundle:
    tests: tuple[str, ...]
    general: tuple[str, ...]
    duplicates: tuple[str, ...]


def _extract_runtime(
    definition: ToolDefinition,
    strategies: Mapping[str, StrategyDefinition],
) -> _RuntimeConfig:
    runtime = definition.runtime
    kind = _normalize_runtime_kind(runtime.kind if runtime is not None else None, context=definition.name)
    package = runtime.package if runtime is not None else None
    min_version = runtime.min_version if runtime is not None else None
    version_command = _normalize_version_command(
        runtime.version_command if runtime is not None else None,
        context=definition.name,
    )
    installers: tuple[InstallerCallable, ...] = ()
    if runtime is not None and runtime.install is not None:
        installers = (
            _instantiate_installer(
                runtime.install,
                strategies,
                context=definition.name,
            ),
        )
    return _RuntimeConfig(
        kind=kind,
        package=package,
        min_version=min_version,
        version_command=version_command,
        installers=installers,
    )


def _normalize_phase_literal(raw: str, *, context: str) -> PhaseLiteral:
    """Return the validated execution phase literal for ``raw``.

    Args:
        raw: Phase identifier sourced from catalog metadata.
        context: Human-readable context used for error messages.

    Returns:
        PhaseLiteral: Validated execution phase.

    Raises:
        CatalogIntegrityError: If ``raw`` is not a supported phase identifier.
    """

    literal = PHASE_LITERAL_MAP.get(raw)
    if literal is None:
        raise CatalogIntegrityError(f"{context}: unsupported phase '{raw}'")
    return literal


def _normalize_runtime_kind(raw: RuntimeType | str | None, *, context: str) -> ToolRuntimeKind:
    if raw is None:
        return DEFAULT_RUNTIME_KIND
    candidate = str(raw)
    literal = RUNTIME_LITERAL_MAP.get(candidate)
    if literal is None:
        raise CatalogIntegrityError(f"{context}: unsupported runtime '{candidate}'")
    return literal


def _normalize_version_command(value: Sequence[str] | str | None, *, context: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return tuple(str(entry) for entry in value)
    if isinstance(value, str):
        return (value,)
    raise CatalogIntegrityError(
        f"{context}: runtime version command must be a string or sequence of strings",
    )


def _extract_suppressions(bundle: SuppressionsDefinition | None) -> _SuppressionBundle:
    if bundle is None:
        return _SuppressionBundle(tests=(), general=(), duplicates=())
    return _SuppressionBundle(
        tests=tuple(bundle.tests),
        general=tuple(bundle.general),
        duplicates=tuple(bundle.duplicates),
    )
