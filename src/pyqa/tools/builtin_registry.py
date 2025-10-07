# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Registry wiring for built-in and catalog-driven tool definitions."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

from pyqa.platform.paths import get_pyqa_root

from ..catalog.errors import CatalogIntegrityError
from ..catalog.loader import ToolCatalogLoader
from ..catalog.model_catalog import CatalogSnapshot
from ..catalog.model_runtime import SUPPORTED_RUNTIME_TYPES
from ..catalog.model_strategy import StrategyDefinition
from .base import (
    CommandBuilder,
    DeferredCommand,
    InstallerCallable,
    Parser,
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

VALID_RUNTIME_NAMES: Final[set[str]] = set(SUPPORTED_RUNTIME_TYPES)


@dataclass(frozen=True)
class _CatalogCacheEntry:
    """Cached catalog payload containing the snapshot and materialised tools."""

    checksum: str
    snapshot: CatalogSnapshot
    tools: tuple[Tool, ...]


_CATALOG_CACHE: dict[tuple[Path, Path], _CatalogCacheEntry] = {}


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
    definition: Any,
    strategies: Mapping[str, StrategyDefinition],
) -> Tool:
    runtime_config = _extract_runtime(definition, strategies)
    documentation_value = _convert_documentation(getattr(definition, "documentation", None))
    suppressions_tuple = _extract_suppressions(
        getattr(getattr(definition, "diagnostics_bundle", None), "suppressions", None),
    )
    actions = tuple(
        _materialize_action(action, strategies, context=f"{definition.name}:{action.name}")
        for action in getattr(definition, "actions", ())
    )

    tool = Tool(
        name=definition.name,
        actions=actions,
        phase=getattr(definition, "phase", "lint"),
        before=getattr(definition, "before", ()),
        after=getattr(definition, "after", ()),
        languages=getattr(definition, "languages", ()),
        file_extensions=getattr(definition, "file_extensions", ()),
        config_files=getattr(definition, "config_files", ()),
        description=getattr(definition, "description", ""),
        auto_install=getattr(definition, "auto_install", False),
        default_enabled=getattr(definition, "default_enabled", True),
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
    action: Any,
    strategies: Mapping[str, StrategyDefinition],
    *,
    context: str,
) -> ToolAction:
    command_builder = _instantiate_command(action.command.reference, strategies, context=context)
    parser_instance = None
    if action.parser is not None:
        parser_instance = _instantiate_parser(action.parser.reference, strategies, context=context)

    env_mapping = {str(key): str(value) for key, value in getattr(action, "env", {}).items()}

    description = getattr(action, "description", "") or ""
    filters = tuple(getattr(action, "filters", ()))

    return ToolAction(
        name=action.name,
        command=command_builder,
        is_fix=getattr(action, "is_fix", False),
        append_files=getattr(action, "append_files", True),
        filter_patterns=filters,
        ignore_exit=getattr(action, "ignore_exit", False),
        description=description,
        timeout_s=getattr(action, "timeout_seconds", None),
        env=env_mapping,
        parser=parser_instance,
    )


def _instantiate_command(
    reference: Any,
    strategies: Mapping[str, StrategyDefinition],
    *,
    context: str,
) -> CommandBuilder:
    strategy_definition = strategies.get(reference.strategy)
    if strategy_definition is None:
        raise CatalogIntegrityError(f"{context}: unknown command strategy '{reference.strategy}'")
    if strategy_definition.strategy_type != COMMAND_STRATEGY:
        raise CatalogIntegrityError(
            f"{context}: strategy '{reference.strategy}' is not a command strategy",
        )
    factory = _resolve_strategy_callable(strategy_definition)
    config = _as_plain_json(reference.config)
    instance = _call_strategy_factory(factory, config)
    return _ensure_command_builder(instance, context=context)


def _instantiate_parser(
    reference: Any,
    strategies: Mapping[str, StrategyDefinition],
    *,
    context: str,
) -> Parser:
    strategy_definition = strategies.get(reference.strategy)
    if strategy_definition is None:
        raise CatalogIntegrityError(f"{context}: unknown parser strategy '{reference.strategy}'")
    if strategy_definition.strategy_type != PARSER_STRATEGY:
        raise CatalogIntegrityError(
            f"{context}: strategy '{reference.strategy}' is not a parser strategy",
        )
    factory = _resolve_strategy_callable(strategy_definition)
    config = _as_plain_json(reference.config)
    parser = cast(Parser, _call_strategy_factory(factory, config))
    if not hasattr(parser, "parse"):
        raise CatalogIntegrityError(f"{context}: parser strategy did not return a parser instance")
    return parser


def _instantiate_installer(
    reference: Any,
    strategies: Mapping[str, StrategyDefinition],
    *,
    context: str,
) -> InstallerCallable:
    strategy_definition = strategies.get(reference.strategy)
    if strategy_definition is None:
        raise CatalogIntegrityError(f"{context}: unknown installer strategy '{reference.strategy}'")
    if strategy_definition.strategy_type != INSTALLER_STRATEGY:
        raise CatalogIntegrityError(
            f"{context}: strategy '{reference.strategy}' is not an installer strategy",
        )
    factory = _resolve_strategy_callable(strategy_definition)
    config = _as_plain_json(getattr(reference, "config", {}))
    installer = _call_strategy_factory(factory, config)
    if not callable(installer):
        raise CatalogIntegrityError(
            f"{context}: installer strategy '{reference.strategy}' did not return a callable",
        )
    return cast(InstallerCallable, installer)


def _convert_documentation(bundle: Any) -> ToolDocumentation | None:
    if bundle is None:
        return None
    help_entry = _to_tool_doc_entry(getattr(bundle, "help", None))
    command_entry = _to_tool_doc_entry(getattr(bundle, "command", None))
    shared_entry = _to_tool_doc_entry(getattr(bundle, "shared", None))
    if help_entry is None and command_entry is None and shared_entry is None:
        return None
    return ToolDocumentation(help=help_entry, command=command_entry, shared=shared_entry)


def _to_tool_doc_entry(entry: Any) -> ToolDocumentationEntry | None:
    if entry is None:
        return None
    format_value = getattr(entry, "format", "text")
    content_value = getattr(entry, "content", None)
    if content_value is None:
        return None
    return ToolDocumentationEntry(format=str(format_value), content=str(content_value))


def _resolve_strategy_callable(definition: StrategyDefinition) -> Callable[..., Any]:
    return definition.resolve_callable()


def _call_strategy_factory(factory: Callable[..., Any], config: Mapping[str, Any]) -> Any:
    try:
        return factory(config)
    except TypeError:
        if config:
            raise
        return factory()


def _ensure_command_builder(instance: Any, *, context: str) -> CommandBuilder:
    if hasattr(instance, "build") and callable(instance.build):
        return cast(CommandBuilder, instance)
    if isinstance(instance, Sequence) and not isinstance(instance, (str, bytes, bytearray)):
        deferred = DeferredCommand(tuple(str(part) for part in instance))
        return cast(CommandBuilder, deferred)
    raise CatalogIntegrityError(
        f"{context}: command strategy did not return a valid command builder",
    )


def _as_plain_json(value: Any) -> Any:
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
    definition: Any,
    strategies: Mapping[str, StrategyDefinition],
) -> _RuntimeConfig:
    runtime = getattr(definition, "runtime", None)
    kind = _normalize_runtime_kind(getattr(runtime, "kind", None), context=definition.name)
    package = getattr(runtime, "package", None) if runtime is not None else None
    min_version = getattr(runtime, "min_version", None) if runtime is not None else None
    version_command = _normalize_version_command(
        getattr(runtime, "version_command", None) if runtime is not None else None,
        context=definition.name,
    )
    installers: tuple[InstallerCallable, ...] = ()
    if runtime is not None and getattr(runtime, "install", None) is not None:
        installers = (
            _instantiate_installer(
                runtime.install,
                strategies,
                context=definition.name,
            ),
        )
    return _RuntimeConfig(
        kind=kind,
        package=str(package) if package is not None else None,
        min_version=str(min_version) if min_version is not None else None,
        version_command=version_command,
        installers=installers,
    )


def _normalize_runtime_kind(raw: Any, *, context: str) -> ToolRuntimeKind:
    candidate = getattr(raw, "value", raw)
    if candidate is None:
        return DEFAULT_RUNTIME_KIND
    candidate_str = str(candidate)
    if candidate_str not in VALID_RUNTIME_NAMES:
        raise CatalogIntegrityError(
            f"{context}: unsupported runtime '{candidate_str}'",
        )
    return cast(ToolRuntimeKind, candidate_str)


def _normalize_version_command(value: Any, *, context: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return tuple(str(entry) for entry in value)
    if isinstance(value, str):
        return (value,)
    raise CatalogIntegrityError(
        f"{context}: runtime version command must be a string or sequence of strings",
    )


def _extract_suppressions(bundle: Any) -> _SuppressionBundle:
    if bundle is None:
        return _SuppressionBundle(tests=(), general=(), duplicates=())
    return _SuppressionBundle(
        tests=tuple(getattr(bundle, "tests", ()) or ()),
        general=tuple(getattr(bundle, "general", ()) or ()),
        duplicates=tuple(getattr(bundle, "duplicates", ()) or ()),
    )
