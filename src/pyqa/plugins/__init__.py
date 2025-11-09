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
from functools import partial
from importlib import import_module, metadata
from importlib.metadata import EntryPoint, EntryPoints
from types import ModuleType, SimpleNamespace
from typing import TypeAlias, TypeVar, cast

import typer

from pyqa.cli.protocols import CommandCallable, CommandDecorator, TyperLike, TyperSubApplication
from tooling_spec.catalog.plugins import CatalogContribution
from tooling_spec.catalog.types import JSONValue as CatalogJSONValue


class _FallbackTyper(TyperLike):
    """Fallback shim used when Typer is not installed."""

    def __init__(self) -> None:
        """Initialise a Typer-like stand-in with no runtime behaviour."""

        self._commands: dict[str, CommandCallable] = {}
        self._callbacks: list[CommandCallable] = []

    def register_command(self, name: str, func: CommandCallable) -> None:
        """Record ``func`` under ``name`` for test visibility.

        Args:
            name: Command identifier registered with the CLI.
            func: Callable executed when the command is invoked.
        """

        self._commands[name] = func

    def command(
        self,
        name: str | None = None,
        *,
        help_text: str | None = None,
        add_help_option: bool = True,
        hidden: bool = False,
    ) -> CommandDecorator:
        """Return a decorator that records commands without execution.

        Args:
            name: Optional command identifier to associate with the decorated function.
            help_text: Ignored help text maintained for signature compatibility.
            add_help_option: Ignored flag maintained for signature compatibility.
            hidden: Ignored flag maintained for signature compatibility.

        Returns:
            CommandDecorator: Decorator that stores the function and returns it unchanged.
        """

        del help_text, add_help_option, hidden
        return cast(CommandDecorator, partial(self._record_command, name=name))

    def callback(
        self,
        *,
        invoke_without_command: bool = False,
    ) -> CommandDecorator:
        """Return a decorator that records callbacks for inspection.

        Args:
            invoke_without_command: Flag indicating whether the callback executes without a sub-command.

        Returns:
            CommandDecorator: Decorator that stores the callback and returns it unchanged.
        """

        del invoke_without_command
        return cast(CommandDecorator, self._record_callback)

    def add_typer(self, sub_command: TyperSubApplication | typer.Typer, *, name: str | None = None) -> None:
        """Record nested Typer applications for completeness in tests.

        Args:
            sub_command: Typer-compatible application being registered as a sub-command.
            name: Optional command name associated with ``sub_command``.
        """

        del sub_command, name

    def __call__(self) -> None:
        """Raise an informative error when attempting to invoke the fallback."""

        raise RuntimeError("Typer is unavailable in this environment") from None

    def _record_command(self, func: CommandCallable, *, name: str | None) -> CommandCallable:
        """Record ``func`` under ``name`` and return the callable unchanged.

        Args:
            func: Command callable registered with the fallback Typer.
            name: Optional command identifier used for registration.

        Returns:
            CommandCallable: The original callable provided by the caller.
        """

        command_name = name or func.__name__
        self.register_command(command_name, func)
        return func

    def _record_callback(self, func: CommandCallable) -> CommandCallable:
        """Record a callback to mirror Typer's application-level decorators.

        Args:
            func: Callback callable registered with the fallback Typer.

        Returns:
            CommandCallable: The original callable provided by the caller.
        """

        self._callbacks.append(func)
        return func


def _resolve_typer() -> type[TyperLike]:
    """Return the Typer application class or a fallback stand-in.

    Returns:
        type[TyperLike]: Concrete Typer class or the local fallback implementation.
    """

    try:
        module: ModuleType = import_module("typer")
    except ModuleNotFoundError:  # pragma: no cover - typer may be unavailable
        return _FallbackTyper
    typer_cls = getattr(module, "Typer", None)
    if not isinstance(typer_cls, type):
        return _FallbackTyper
    return cast(type[TyperLike], typer_cls)


Typer = _resolve_typer()


CATALOG_PLUGIN_GROUP = "pyqa.catalog.plugins"
CLI_PLUGIN_GROUP = "pyqa.cli.plugins"
DIAGNOSTICS_PLUGIN_GROUP = "pyqa.diagnostics.plugins"

CatalogPluginFactory: TypeAlias = Callable[..., CatalogContribution]
CLIPluginFactory: TypeAlias = Callable[[TyperLike], None]
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
