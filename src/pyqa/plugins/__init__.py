# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Entry-point plugin loading helpers.

These helpers provide a thin abstraction around :mod:`importlib.metadata`
so that future packages can contribute catalog, CLI, or diagnostics
extensions without modifying the core code base.  The public functions
return tuples to keep results hashable and to discourage accidental
mutation of the loaded plugin sequences.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from importlib import metadata
from importlib.metadata import EntryPoint, EntryPoints
from types import SimpleNamespace
from typing import TYPE_CHECKING, TypeAlias, TypeVar, cast

from tooling_spec.catalog.plugins import CatalogContribution
from tooling_spec.catalog.types import JSONValue as CatalogJSONValue

if TYPE_CHECKING:
    from typer import Typer
else:  # pragma: no cover - typer may be unavailable in minimal environments
    try:
        from typer import Typer
    except ModuleNotFoundError:  # pragma: no cover - fallback stub for tooling tests

        class Typer:
            """Fallback shim used when Typer is not installed."""

            def __init__(self) -> None:
                """Initialise a Typer-like stub with no runtime behaviour."""

                self._commands: dict[str, Callable[..., None]] = {}

            def register_command(self, name: str, func: Callable[..., None]) -> None:
                """Record ``func`` under ``name`` for test visibility."""

                self._commands[name] = func

            def command(self, name: str) -> Callable[[Callable[..., _FactoryT]], Callable[..., _FactoryT]]:
                """Return a decorator that records the command without executing."""

                def decorator(func: Callable[..., _FactoryT]) -> Callable[..., _FactoryT]:
                    self.register_command(name, cast(Callable[..., None], func))
                    return func

                return decorator

            def __call__(self) -> None:
                """Raise an informative error when attempting to invoke the stub."""

                raise RuntimeError("Typer is unavailable in this environment") from None


CATALOG_PLUGIN_GROUP = "pyqa.catalog.plugins"
CLI_PLUGIN_GROUP = "pyqa.cli.plugins"
DIAGNOSTICS_PLUGIN_GROUP = "pyqa.diagnostics.plugins"

CatalogPluginFactory: TypeAlias = Callable[..., CatalogContribution]
CLIPluginFactory: TypeAlias = Callable[[Typer], None]
DiagnosticsPlugin: TypeAlias = Callable[..., None] | str | Mapping[str, CatalogJSONValue]

_EntryPointSource: TypeAlias = EntryPoints | Mapping[str, Sequence[EntryPoint]]
_FactoryT = TypeVar("_FactoryT")


def noop_plugin(invocation: Mapping[str, CatalogJSONValue] | None = None) -> None:
    """Default plugin callable used as a placeholder.

    Args:
        invocation: Optional invocation payload supplied by the caller.
    """

    del invocation


def _select_entry_points(entries: _EntryPointSource, group: str) -> Iterable[EntryPoint]:
    """Return entry points exposed under ``group`` from ``entries``.

    Args:
        entries: Raw entry-point container returned by :func:`metadata.entry_points`.
        group: Name of the entry-point group to extract.

    Returns:
        Iterable[EntryPoint]: Entry points belonging to ``group``. When the
        container lacks the requested group an empty iterable is returned.
    """

    if isinstance(entries, Mapping):
        return entries.get(group, ())
    if hasattr(entries, "select"):
        return entries.select(group=group)
    return ()


def _discover_entry_points(group: str, loader: Callable[[EntryPoint], _FactoryT]) -> tuple[_FactoryT, ...]:
    """Return callables exposed by the entry-point ``group``.

    Args:
        group: Entry-point group name to inspect.
        loader: Callable that converts an :class:`EntryPoint` into the desired plugin type.

    Returns:
        tuple[_FactoryT, ...]: Loaded plugins associated with ``group``. Entries that fail to import
        are skipped silently to avoid destabilising the caller.
    """

    entries_raw = metadata.entry_points()
    selected = _select_entry_points(cast(_EntryPointSource, entries_raw), group)

    callables: list[_FactoryT] = []
    for entry in selected:
        try:
            plugin = loader(entry)
        except (AttributeError, ImportError, ValueError, RuntimeError):
            continue
        callables.append(plugin)
    return tuple(callables)


def load_catalog_plugins() -> tuple[CatalogPluginFactory, ...]:
    """Return catalog plugin factories discovered via entry points.

    Returns:
        tuple[CatalogPluginFactory, ...]: Sequence of catalog plugin factories.
    """

    return _discover_entry_points(
        CATALOG_PLUGIN_GROUP,
        loader=lambda entry: cast(CatalogPluginFactory, entry.load()),
    )


def load_cli_plugins() -> tuple[CLIPluginFactory, ...]:
    """Return CLI plugin factories discovered via entry points.

    Returns:
        tuple[CLIPluginFactory, ...]: Sequence of CLI plugin factories.
    """

    return _discover_entry_points(
        CLI_PLUGIN_GROUP,
        loader=lambda entry: cast(CLIPluginFactory, entry.load()),
    )


def load_diagnostics_plugins() -> tuple[DiagnosticsPlugin, ...]:
    """Return diagnostics plugins discovered via entry points.

    Diagnostics plugins may be simple descriptors or callables depending on the
    consuming subsystem, so the helper preserves their native types.

    Returns:
        tuple[DiagnosticsPlugin, ...]: Sequence of diagnostics plugins.
    """

    return _discover_entry_points(
        DIAGNOSTICS_PLUGIN_GROUP,
        loader=lambda entry: cast(DiagnosticsPlugin, entry.load()),
    )


def load_all_plugins() -> SimpleNamespace:
    """Return a namespace bundling all plugin groups for convenience.

    Returns:
        SimpleNamespace: Namespace exposing catalog, CLI, and diagnostics plugins.
    """

    return SimpleNamespace(
        catalog=load_catalog_plugins(),
        cli=load_cli_plugins(),
        diagnostics=load_diagnostics_plugins(),
    )


__all__ = [
    "CATALOG_PLUGIN_GROUP",
    "CLI_PLUGIN_GROUP",
    "DIAGNOSTICS_PLUGIN_GROUP",
    "noop_plugin",
    "load_all_plugins",
    "load_catalog_plugins",
    "load_cli_plugins",
    "load_diagnostics_plugins",
]
