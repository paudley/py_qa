# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Custom Typer helpers for consistent, sorted CLI help output."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import typer
from click.core import Parameter
from typer.core import TyperCommand, TyperGroup, _


class SortedTyperCommand(TyperCommand):
    """Typer command that renders options in sorted order within help output."""

    def format_options(self, ctx, formatter) -> None:  # type: ignore[override]
        args: list[tuple[str, str]] = []
        option_entries: list[tuple[tuple[str, int], tuple[str, str]]] = []

        for index, param in enumerate(self.get_params(ctx)):
            record = param.get_help_record(ctx)
            if record is None:
                continue
            kind = getattr(param, "param_type_name", "")
            if kind == "argument":
                args.append(record)
            else:
                key = (_primary_option_name(param), index)
                option_entries.append((key, record))

        if args:
            with formatter.section(_("Arguments")):
                formatter.write_dl(args)

        if option_entries:
            sorted_records = [
                record for _, record in sorted(option_entries, key=lambda item: item[0])
            ]
            with formatter.section(_("Options")):
                formatter.write_dl(sorted_records)


class SortedTyperGroup(TyperGroup):
    """Typer group that defaults to using :class:`SortedTyperCommand`."""

    command_class = SortedTyperCommand


class SortedTyper(typer.Typer):
    """Typer application that emits sorted option listings by default."""

    def __init__(self, *args: Any, cls: type[TyperGroup] | None = None, **kwargs: Any) -> None:
        group_cls = cls or SortedTyperGroup
        super().__init__(*args, cls=group_cls, **kwargs)

    def command(
        self,
        name: str | None = None,
        *,
        cls: type[TyperCommand] | None = None,
        **kwargs: Any,
    ):  # type: ignore[override]
        if cls is None:
            cls = SortedTyperCommand
        return super().command(name, cls=cls, **kwargs)


def create_typer(*, cls: type[TyperGroup] | None = None, **kwargs: Any) -> SortedTyper:
    """Return a :class:`SortedTyper` configured to emit sorted help listings."""
    return SortedTyper(cls=cls, **kwargs)


def _primary_option_name(param: Parameter) -> str:
    """Return the canonical name used for sorting a Click parameter."""
    option_names: Iterable[str] = tuple(getattr(param, "opts", ())) + tuple(
        getattr(param, "secondary_opts", ()),
    )
    long_names = [name for name in option_names if name.startswith("--")]
    candidate = long_names[0] if long_names else (next(iter(option_names), "") or param.name or "")
    return candidate.lstrip("-").lower()
