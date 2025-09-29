# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Registry wiring for built-in and catalog-driven tool definitions."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..tooling import CatalogIntegrityError, CatalogSnapshot, ToolCatalogLoader
from ..tooling.loader import StrategyDefinition
from .base import (
    DeferredCommand,
    Tool,
    ToolAction,
    ToolContext,
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


@dataclass(frozen=True)
class _CatalogCacheEntry:
    """Cached catalog payload containing the snapshot and materialised tools."""

    checksum: str
    snapshot: CatalogSnapshot
    tools: tuple[Tool, ...]


_CATALOG_CACHE: dict[tuple[Path, Path], _CatalogCacheEntry] = {}


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
    base = Path(__file__).resolve()
    project_root = base.parents[3]
    catalog = project_root / "tooling" / "catalog"
    if catalog.exists():
        return catalog
    alt_catalog = base.parents[1] / "tooling" / "catalog"
    if alt_catalog.exists():
        return alt_catalog
    raise FileNotFoundError("Unable to locate tooling/catalog directory")


def _materialize_tool(
    definition: Any,
    strategies: Mapping[str, StrategyDefinition],
) -> Tool:
    runtime = getattr(definition, "runtime", None)
    documentation_bundle = getattr(definition, "documentation", None)
    documentation_value = _convert_documentation(documentation_bundle)
    runtime_kind = getattr(runtime, "kind", "python") if runtime is not None else "python"
    package = getattr(runtime, "package", None) if runtime is not None else None
    min_version = getattr(runtime, "min_version", None) if runtime is not None else None
    version_command = getattr(runtime, "version_command", None) if runtime is not None else None
    suppressions = getattr(definition.diagnostics_bundle, "suppressions", None)
    suppressions_tests = suppressions.tests if suppressions is not None else ()
    suppressions_general = suppressions.general if suppressions is not None else ()
    suppressions_duplicates = suppressions.duplicates if suppressions is not None else ()

    installers: list[Callable[[ToolContext], None]] = []
    install_def = getattr(runtime, "install", None)
    if install_def is not None:
        installers.append(
            _instantiate_installer(
                install_def,
                strategies,
                context=definition.name,
            ),
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
        runtime=runtime_kind,
        package=package,
        min_version=min_version,
        version_command=version_command,
        suppressions_tests=suppressions_tests,
        suppressions_general=suppressions_general,
        suppressions_duplicates=suppressions_duplicates,
        installers=tuple(installers),
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
) -> Any:
    strategy_definition = strategies.get(reference.strategy)
    if strategy_definition is None:
        raise CatalogIntegrityError(f"{context}: unknown command strategy '{reference.strategy}'")
    if strategy_definition.strategy_type != "command":
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
) -> Any:
    strategy_definition = strategies.get(reference.strategy)
    if strategy_definition is None:
        raise CatalogIntegrityError(f"{context}: unknown parser strategy '{reference.strategy}'")
    if strategy_definition.strategy_type != "parser":
        raise CatalogIntegrityError(
            f"{context}: strategy '{reference.strategy}' is not a parser strategy",
        )
    factory = _resolve_strategy_callable(strategy_definition)
    config = _as_plain_json(reference.config)
    parser = _call_strategy_factory(factory, config)
    if not hasattr(parser, "parse"):
        raise CatalogIntegrityError(f"{context}: parser strategy did not return a parser instance")
    return parser


def _instantiate_installer(
    reference: Any,
    strategies: Mapping[str, StrategyDefinition],
    *,
    context: str,
) -> Callable[[ToolContext], None]:
    strategy_definition = strategies.get(reference.strategy)
    if strategy_definition is None:
        raise CatalogIntegrityError(f"{context}: unknown installer strategy '{reference.strategy}'")
    if strategy_definition.strategy_type != "installer":
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
    return installer


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
    if definition.entry is not None:
        module = importlib.import_module(definition.implementation)
        return getattr(module, definition.entry)
    module_path, _, attribute_name = definition.implementation.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, attribute_name)


def _call_strategy_factory(factory: Callable[..., Any], config: Mapping[str, Any]) -> Any:
    try:
        return factory(config)
    except TypeError:
        if config:
            raise
        return factory()


def _ensure_command_builder(instance: Any, *, context: str) -> Any:
    if hasattr(instance, "build") and callable(instance.build):
        return instance
    if isinstance(instance, Sequence) and not isinstance(instance, (str, bytes, bytearray)):
        return DeferredCommand(tuple(str(part) for part in instance))
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
    if schema_root is None:
        resolved_schema = (resolved_catalog.parent / "schema").resolve()
    else:
        resolved_schema = schema_root.resolve()
    return (resolved_catalog, resolved_schema)
