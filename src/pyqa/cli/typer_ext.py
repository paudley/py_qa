# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Custom Typer helpers for consistent, sorted CLI help output."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

import typer
import typer.main
from click.core import Parameter
from click.formatting import HelpFormatter
from typer.core import TyperCommand, TyperGroup


def _install_param_decl_sanitizer() -> None:
    """Install a guard that strips non-string parameter declarations.

    Returns:
        None: The guard is installed as a side effect on :mod:`typer.main`.

    """

    if getattr(typer.main, "_pyqa_param_sanitizer_installed", False):
        return

    original_get_click_param = typer.main.get_click_param

    def _patched_get_click_param(param: Any) -> tuple[Any, Any]:
        param_decls = getattr(param.default, "param_decls", None)
        if isinstance(param_decls, Sequence):
            sanitized = tuple(decl for decl in param_decls if isinstance(decl, str))
            if len(sanitized) != len(param_decls):
                setattr(param.default, "param_decls", sanitized)
        return original_get_click_param(param)

    typer.main.get_click_param = _patched_get_click_param
    setattr(typer.main, "_pyqa_param_sanitizer_installed", True)


_install_param_decl_sanitizer()


class SortedTyperCommand(TyperCommand):
    """Typer command that renders options in sorted order within help output."""

    def format_options(
        self,
        ctx: typer.Context,
        formatter: HelpFormatter,
    ) -> None:  # type: ignore[override]
        """Render positional arguments and sorted options within CLI help.

        Args:
            ctx: Typer context describing the application invocation.
            formatter: Click help formatter used to emit definition lists.

        Returns:
            None: The formatter is mutated in place with the rendered output.

        """

        argument_records: list[tuple[str, str]] = []
        option_entries: list[tuple[tuple[str, int], tuple[str, str]]] = []

        for index, param in enumerate(self.get_params(ctx)):
            record = param.get_help_record(ctx)
            if record is None:
                continue
            if getattr(param, "param_type_name", "") == "argument":
                argument_records.append(record)
                continue
            option_entries.append(((_primary_option_name(param), index), record))

        if argument_records:
            with formatter.section("Arguments"):
                formatter.write_dl(argument_records)

        if option_entries:
            sorted_records = [entry for _, entry in sorted(option_entries, key=lambda item: item[0])]
            with formatter.section("Options"):
                formatter.write_dl(sorted_records)


class SortedTyperGroup(TyperGroup):
    """Typer group that defaults to using :class:`SortedTyperCommand`."""

    command_class = SortedTyperCommand


class SortedTyper(typer.Typer):
    """Typer application that emits sorted option listings by default."""

    def __init__(self, *args: Any, cls: type[TyperGroup] | None = None, **kwargs: Any) -> None:
        """Initialise the Typer application with sorted help semantics.

        Args:
            *args: Positional arguments forwarded to :class:`typer.Typer`.
            cls: Optional group class to override the default sorted group.
            **kwargs: Keyword arguments forwarded to :class:`typer.Typer`.

        Returns:
            None

        """

        group_cls = cls or SortedTyperGroup
        super().__init__(*args, cls=group_cls, **kwargs)

    def command(
        self,
        name: str | None = None,
        *,
        cls: type[TyperCommand] | None = None,
        **kwargs: Any,
    ) -> Callable[[Callable[..., Any]], typer.Command]:  # type: ignore[override]
        """Return a decorator that registers commands using sorted help output.

        Args:
            name: Optional explicit command name.
            cls: Command class to instantiate; defaults to
                :class:`SortedTyperCommand` when ``None``.
            **kwargs: Additional keyword arguments forwarded to the base
                :meth:`typer.Typer.command` implementation.

        Returns:
            Callable[[Callable[..., Any]], typer.Command]: Decorator that
            registers the wrapped callable as a Typer command.

        """

        if cls is None:
            cls = SortedTyperCommand
        return super().command(name, cls=cls, **kwargs)


def create_typer(*, cls: type[TyperGroup] | None = None, **kwargs: Any) -> SortedTyper:
    """Return a :class:`SortedTyper` configured to emit sorted help listings.

    Args:
        cls: Optional Typer group subclass controlling command creation.
        **kwargs: Additional arguments forwarded to :class:`SortedTyper`.

    Returns:
        SortedTyper: Configured Typer application with sorted help output.

    """
    return SortedTyper(cls=cls, **kwargs)


def _primary_option_name(param: Parameter) -> str:
    """Return the canonical name used for sorting a Click parameter.

    Args:
        param: Click parameter being inspected.

    Returns:
        str: Normalised option name (without leading dashes) for sorting.

    """
    option_names: Iterable[str] = tuple(getattr(param, "opts", ())) + tuple(
        getattr(param, "secondary_opts", ()),
    )
    long_names = [name for name in option_names if name.startswith("--")]
    candidate = long_names[0] if long_names else (next(iter(option_names), "") or param.name or "")
    return candidate.lstrip("-").lower()
