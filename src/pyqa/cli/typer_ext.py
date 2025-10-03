# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Custom Typer helpers for consistent, sorted CLI help output."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar, get_args, get_origin, get_type_hints

import click
import typer
import typer.main
from click.core import Context, Parameter
from click.formatting import HelpFormatter
from typer.core import TyperCommand, TyperGroup
from typer.models import OptionInfo, ParameterInfo

from .shared import Depends


@dataclass(slots=True)
class _DependencyMeta:
    param_name: str
    dependency: Callable[..., Any]
    cli_param_names: set[str]
    context_param_name: str | None


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

    _install_dependency_support(original_get_click_param)


def _install_dependency_support(original_get_click_param: Callable[[Any], tuple[Any, Any]]) -> None:
    if getattr(typer.main, "_pyqa_dependency_support_installed", False):
        return

    original_get_params = typer.main.get_params_convertors_ctx_param_name_from_function
    original_get_callback = typer.main.get_callback

    def _analyze_callback(callback: Callable[..., Any]):
        if getattr(callback, "__pyqa_analyzed__", False):
            return (
                getattr(callback, "__pyqa_params__"),
                getattr(callback, "__pyqa_convertors__"),
                getattr(callback, "__pyqa_context_param__"),
            )

        if callback is None:
            return [], {}, None

        signature = inspect.signature(callback)
        try:
            type_hints = get_type_hints(callback, include_extras=True)
        except Exception:  # pragma: no cover - defensive fallback
            type_hints = {}
        params: list[Any] = []
        convertors: dict[str, Callable[[Any], Any]] = {}
        cli_param_names: set[str] = set()
        dependencies: list[_DependencyMeta] = []
        context_param_name: str | None = None

        for param_name, param in signature.parameters.items():
            annotation = type_hints.get(param_name, param.annotation)
            dependency_info: Depends | None = None
            if annotation is inspect._empty:
                annotation = str
            origin = get_origin(annotation)
            parameter_info: ParameterInfo | None = None
            if origin is Annotated:
                base, *metadata = get_args(annotation)
                annotation = base
                for meta in metadata:
                    if isinstance(meta, Depends):
                        dependency_info = meta
                    elif isinstance(meta, ParameterInfo):
                        parameter_info = meta
            if isinstance(param.default, ParameterInfo) and parameter_info is None:
                parameter_info = param.default
            if inspect.isclass(annotation) and issubclass(annotation, click.Context):
                context_param_name = param_name
                continue

            if dependency_info is not None:
                dependency_callable = dependency_info.dependency
                dep_params, dep_convertors, dep_context = _analyze_callback(dependency_callable)
                params.extend(dep_params)
                convertors.update(dep_convertors)
                dep_cli_names = getattr(dependency_callable, "__pyqa_cli_param_names__", set())
                dependencies.append(
                    _DependencyMeta(
                        param_name=param_name,
                        dependency=dependency_callable,
                        cli_param_names=dep_cli_names,
                        context_param_name=dep_context,
                    )
                )
                cli_param_names.update(dep_cli_names)
                continue

            if parameter_info is None:
                parameter_info = OptionInfo()
            updated_param = param.replace(annotation=annotation, default=parameter_info)
            click_param, convertor = original_get_click_param(updated_param)
            params.append(click_param)
            if convertor:
                convertors[param_name] = convertor
            cli_param_names.add(param_name)

        setattr(callback, "__pyqa_params__", params)
        setattr(callback, "__pyqa_convertors__", convertors)
        setattr(callback, "__pyqa_context_param__", context_param_name)
        setattr(callback, "__pyqa_dependencies__", dependencies)
        setattr(callback, "__pyqa_cli_param_names__", cli_param_names)
        setattr(callback, "__pyqa_analyzed__", True)
        return params, convertors, context_param_name

    def _resolve_dependencies(
        callback: Callable[..., Any],
        values: dict[str, Any],
        context: click.Context,
    ) -> None:
        dependencies: list[_DependencyMeta] = getattr(callback, "__pyqa_dependencies__", [])
        for meta in dependencies:
            dep_values: dict[str, Any] = {}
            for name in meta.cli_param_names:
                if name in values:
                    dep_values[name] = values.pop(name)
            if meta.context_param_name:
                dep_values[meta.context_param_name] = context
            _resolve_dependencies(meta.dependency, dep_values, context)
            sig = inspect.signature(meta.dependency)
            call_kwargs = {name: dep_values[name] for name in sig.parameters if name in dep_values}
            result = meta.dependency(**call_kwargs)
            values[meta.param_name] = result

    def _patched_get_params(callback: Callable[..., Any]):
        params, convertors, context_param_name = _analyze_callback(callback)
        return params, convertors, context_param_name

    get_params_from_function = typer.main.get_params_from_function

    def _patched_get_callback(
        *,
        callback: Callable[..., Any] | None = None,
        params: Iterable[Any] = (),
        convertors: dict[str, Callable[[Any], Any]] | None = None,
        context_param_name: str | None = None,
        pretty_exceptions_short: bool,
    ) -> Callable[..., Any] | None:
        if callback is None:
            return None

        use_convertors = convertors or {}
        parameters = get_params_from_function(callback)

        def _default_for_parameter(meta: Any) -> Any:
            default_candidate = getattr(meta, "default", None)
            return getattr(default_candidate, "default", default_candidate)

        defaults = {name: _default_for_parameter(meta) for name, meta in parameters.items()}

        def wrapper(*call_args: Any, **kwargs: Any) -> Any:
            context = call_args[0] if call_args else click.get_current_context()
            if call_args[1:]:  # pragma: no cover - defensive guard for unexpected usage
                raise TypeError("Positional arguments beyond the Typer context are not supported.")

            values: dict[str, Any] = dict(defaults)
            for key, value in kwargs.items():
                if key in use_convertors:
                    if value is None:
                        values[key] = values.get(key)
                    else:
                        values[key] = use_convertors[key](value)
                else:
                    values[key] = value if value is not None else values.get(key)
            if context_param_name:
                values[context_param_name] = context
            _resolve_dependencies(callback, values, context)
            call_signature = inspect.signature(callback)
            call_kwargs = {name: values[name] for name in call_signature.parameters if name in values}
            return callback(**call_kwargs)

        return wrapper

    typer.main.get_params_convertors_ctx_param_name_from_function = _patched_get_params
    typer.main.get_callback = _patched_get_callback
    setattr(typer.main, "_pyqa_dependency_support_installed", True)


class SortedTyperCommand(TyperCommand):
    """Typer command that renders options in sorted order within help output."""

    def format_options(
        self,
        ctx: Context,
        formatter: HelpFormatter,
    ) -> None:
        """Render positional arguments and sorted options within CLI help.

        Args:
            ctx: Click context describing the application invocation.
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


CommandCallback = TypeVar("CommandCallback", bound=Callable[..., Any])


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
    ) -> Callable[[CommandCallback], CommandCallback]:
        """Return a decorator that registers commands using sorted help output.

        Args:
            name: Optional explicit command name.
            cls: Command class to instantiate; defaults to
                :class:`SortedTyperCommand` when ``None``.
            **kwargs: Additional keyword arguments forwarded to the base
                :meth:`typer.Typer.command` implementation.

        Returns:
            Callable[[CommandCallback], CommandCallback]: Decorator that
            registers the wrapped callable as a Typer command while
            preserving the original callback signature.

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


_install_param_decl_sanitizer()
