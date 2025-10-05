"""Entry-point plugin loading helpers.

These helpers provide a thin abstraction around :mod:`importlib.metadata`
so that future packages can contribute catalog, CLI, or diagnostics
extensions without modifying the core code base.  The public functions
return tuples to keep results hashable and to discourage accidental
mutation of the loaded plugin sequences.
"""

from __future__ import annotations

from importlib import metadata
from types import SimpleNamespace
from typing import Any
from collections.abc import Callable, Iterable, Sequence

CATALOG_PLUGIN_GROUP = "pyqa.catalog.plugins"
CLI_PLUGIN_GROUP = "pyqa.cli.plugins"
DIAGNOSTICS_PLUGIN_GROUP = "pyqa.diagnostics.plugins"

_EntryPointCallable = Callable[..., Any]


def noop_plugin(*_args: Any, **_kwargs: Any) -> None:
    """Default plugin callable used as a placeholder."""

    return None


def _discover_entry_points(group: str) -> Sequence[_EntryPointCallable]:
    """Return callables exposed by the entry-point *group*.

    The helper tolerates importlib API differences between Python versions
    (``entry_points`` returning a mapping vs. an ``EntryPoints`` object) and
    gracefully ignores plugins that fail to resolve.
    """

    try:
        entries = metadata.entry_points()
    except Exception:  # pragma: no cover - metadata import edge case
        return ()

    selected: Iterable[Any]
    if hasattr(entries, "select"):
        selected = entries.select(group=group)
    else:  # pragma: no cover - compatibility path for older metadata API
        selected = entries.get(group, ()) if isinstance(entries, dict) else ()

    callables: list[_EntryPointCallable] = []
    for entry in selected:
        try:
            callables.append(entry.load())
        except Exception:
            continue
    return tuple(callables)


def load_catalog_plugins() -> Sequence[_EntryPointCallable]:
    """Return catalog plugin factories discovered via entry points."""

    return _discover_entry_points(CATALOG_PLUGIN_GROUP)


def load_cli_plugins() -> Sequence[_EntryPointCallable]:
    """Return CLI plugin factories discovered via entry points."""

    return _discover_entry_points(CLI_PLUGIN_GROUP)


def load_diagnostics_plugins() -> Sequence[_EntryPointCallable]:
    """Return diagnostics plugin factories discovered via entry points."""

    return _discover_entry_points(DIAGNOSTICS_PLUGIN_GROUP)


def load_all_plugins() -> SimpleNamespace:
    """Return a namespace bundling all plugin groups for convenience."""

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
