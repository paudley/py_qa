# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Custom Typer helpers for consistent, sorted CLI help output."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Final, TypeVar, get_args, get_origin, get_type_hints

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


@dataclass(slots=True)
class _AnalyzedCallback:
    """Capture Typer callback metadata required to build Click parameters."""

    params: list[Any]
    convertors: dict[str, Callable[[Any], Any]]
    context_param_name: str | None
    dependencies: list[_DependencyMeta]
    cli_param_names: set[str]


@dataclass(slots=True)
class _AnalysisState:
    """Mutable state accumulated while analysing a callback."""

    params: list[Any]
    convertors: dict[str, Callable[[Any], Any]]
    dependencies: list[_DependencyMeta]
    cli_param_names: set[str]
    context_param_name: str | None


@dataclass(slots=True)
class _DirectParameterContext:
    """Container describing a direct parameter without dependency metadata."""

    parameter: inspect.Parameter
    annotation: Any
    parameter_info: ParameterInfo | None


ARGUMENT_PARAM_TYPE: Final[str] = "argument"

ParamsMetadata = tuple[list[Any], dict[str, Callable[[Any], Any]], str | None]
ParamsAdapter = Callable[[Callable[..., Any]], ParamsMetadata]
CallbackAdapter = Callable[..., Callable[..., Any] | None]


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
    """Install dependency-aware Typer patches to support nested callbacks.

    Args:
        original_get_click_param: Typer helper used to translate parameters into
            Click objects prior to installing the dependency-aware shim.

    """

    if getattr(typer.main, "_pyqa_dependency_support_installed", False):
        return

    resolver = _DependencyResolver(original_get_click_param)
    typer.main.get_params_convertors_ctx_param_name_from_function = _build_dependency_param_adapter(resolver)
    typer.main.get_callback = _build_dependency_callback_adapter(resolver)
    setattr(typer.main, "_pyqa_dependency_support_installed", True)


def _build_dependency_param_adapter(
    resolver: _DependencyResolver,
) -> ParamsAdapter:
    """Return a Typer helper that exposes dependency-aware parameter metadata.

    Args:
        resolver: Dependency resolver storing callback analysis results.

    Returns:
        Callable: Adapter returning parameter metadata expected by Typer.

    """

    def _patched_get_params(
        callback: Callable[..., Any],
    ) -> ParamsMetadata:
        analysis = resolver.analyze(callback)
        return analysis.params, analysis.convertors, analysis.context_param_name

    return _patched_get_params


def _build_dependency_callback_adapter(
    resolver: _DependencyResolver,
) -> CallbackAdapter:
    """Return a Typer helper that wires dependency resolution into callbacks.

    Args:
        resolver: Dependency resolver used to hydrate dependencies prior to
            invoking the Typer callback.

    Returns:
        Callable[..., Callable[..., Any] | None]: Adapter returning the wrapped
        callback consumed by Typer.

    """

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

        del params, context_param_name, pretty_exceptions_short
        analysis = resolver.analyze(callback)
        defaults = resolver.build_default_values(callback)
        use_convertors = dict(analysis.convertors)
        if convertors:
            use_convertors.update(convertors)

        def wrapper(*call_args: Any, **kwargs: Any) -> Any:
            context = call_args[0] if call_args else click.get_current_context()
            if call_args[1:]:  # pragma: no cover - defensive guard for unexpected usage
                raise TypeError("Positional arguments beyond the Typer context are not supported.")

            plan = resolver.InvocationPlan(
                analysis=analysis,
                defaults=defaults,
                convertors=use_convertors,
                context=context,
                params=kwargs,
            )
            return resolver.invoke(callback, plan)

        return wrapper

    return _patched_get_callback


class _DependencyResolver:
    """Analyse Typer callbacks and resolve nested dependencies lazily."""

    def __init__(self, original_get_click_param: Callable[[Any], tuple[Any, Any]]) -> None:
        self._get_click_param = original_get_click_param

    # Public API ------------------------------------------------------------------

    def analyze(self, callback: Callable[..., Any] | None) -> _AnalyzedCallback:
        """Return analysis metadata for ``callback`` reusing cached results."""

        if callback is None:
            return _AnalyzedCallback([], {}, None, [], set())
        cached: _AnalyzedCallback | None = getattr(callback, "__pyqa_analysis__", None)
        if cached is not None:
            return cached

        analysis = self._build_analysis(callback)
        self._cache_analysis(callback, analysis)
        return analysis

    def resolve(
        self,
        callback: Callable[..., Any],
        values: dict[str, Any],
        context: click.Context,
    ) -> None:
        """Resolve dependency outputs for ``callback`` and populate ``values``."""

        analysis = self.analyze(callback)
        for meta in analysis.dependencies:
            dep_values = self._extract_dependency_values(values, meta, context)
            self.resolve(meta.dependency, dep_values, context)
            sig = inspect.signature(meta.dependency)
            call_kwargs = {name: dep_values[name] for name in sig.parameters if name in dep_values}
            result = meta.dependency(**call_kwargs)
            values[meta.param_name] = result

    @dataclass(slots=True)
    class InvocationPlan:
        """Describe resolved parameters required to invoke a callback."""

        analysis: _AnalyzedCallback
        defaults: dict[str, Any]
        convertors: dict[str, Callable[[Any], Any]]
        context: click.Context
        params: dict[str, Any]

    def invoke(self, callback: Callable[..., Any], plan: InvocationPlan) -> Any:
        """Invoke ``callback`` with dependency-aware argument resolution."""

        values: dict[str, Any] = dict(plan.defaults)
        for key, value in plan.params.items():
            if key in plan.convertors:
                values[key] = plan.convertors[key](value) if value is not None else values.get(key)
                continue
            if value is not None:
                values[key] = value
            else:
                values[key] = values.get(key)
        if plan.analysis.context_param_name:
            values[plan.analysis.context_param_name] = plan.context
        self.resolve(callback, values, plan.context)
        call_signature = inspect.signature(callback)
        call_kwargs = {name: values[name] for name in call_signature.parameters if name in values}
        return callback(**call_kwargs)

    # Internal helpers ------------------------------------------------------------

    def _build_analysis(self, callback: Callable[..., Any]) -> _AnalyzedCallback:
        signature = inspect.signature(callback)
        type_hints = self._safe_type_hints(callback)

        state = _AnalysisState(
            params=[],
            convertors={},
            dependencies=[],
            cli_param_names=set(),
            context_param_name=None,
        )

        for param_name, parameter in signature.parameters.items():
            self._process_parameter(
                param_name=param_name,
                parameter=parameter,
                type_hints=type_hints,
                state=state,
            )

        return _AnalyzedCallback(
            params=state.params,
            convertors=state.convertors,
            context_param_name=state.context_param_name,
            dependencies=state.dependencies,
            cli_param_names=state.cli_param_names,
        )

    def _cache_analysis(self, callback: Callable[..., Any], analysis: _AnalyzedCallback) -> None:
        """Persist ``analysis`` on ``callback`` for subsequent invocations."""

        setattr(callback, "__pyqa_analysis__", analysis)
        setattr(callback, "__pyqa_params__", analysis.params)
        setattr(callback, "__pyqa_convertors__", analysis.convertors)
        setattr(callback, "__pyqa_context_param__", analysis.context_param_name)
        setattr(callback, "__pyqa_dependencies__", analysis.dependencies)
        setattr(callback, "__pyqa_cli_param_names__", analysis.cli_param_names)
        setattr(callback, "__pyqa_analyzed__", True)

    def _safe_type_hints(self, callback: Callable[..., Any]) -> dict[str, Any]:
        """Return type hints for ``callback`` handling failures defensively."""

        try:
            return get_type_hints(callback, include_extras=True)
        except (
            AttributeError,
            NameError,
            TypeError,
            ValueError,
        ):  # pragma: no cover - defensive fallback
            return {}

    def _parse_annotation(
        self,
        annotation: Any,
        parameter: inspect.Parameter,
    ) -> tuple[Any, ParameterInfo | None, Depends | None]:
        """Return resolved annotation metadata for ``parameter``."""

        dependency_info: Depends | None = None
        parameter_info: ParameterInfo | None = None
        if annotation is inspect.Signature.empty:
            annotation = str
        origin = get_origin(annotation)
        if origin is Annotated:
            base, *metadata = get_args(annotation)
            annotation = base
            for meta in metadata:
                if isinstance(meta, Depends):
                    dependency_info = meta
                elif isinstance(meta, ParameterInfo):
                    parameter_info = meta
        if isinstance(parameter.default, ParameterInfo) and parameter_info is None:
            parameter_info = parameter.default
        return annotation, parameter_info, dependency_info

    def _is_context_parameter(self, annotation: Any) -> bool:
        """Return ``True`` when ``annotation`` requests a Click context."""

        return inspect.isclass(annotation) and issubclass(annotation, click.Context)

    def _build_click_parameter(
        self,
        parameter: inspect.Parameter,
        annotation: Any,
        parameter_info: ParameterInfo | None,
    ) -> tuple[Any, Callable[[Any], Any] | None]:
        """Return the Click parameter + convertor for Typer metadata."""

        info = parameter_info or OptionInfo()
        updated_parameter = parameter.replace(annotation=annotation, default=info)
        return self._get_click_param(updated_parameter)

    def _extract_dependency_values(
        self,
        values: dict[str, Any],
        meta: _DependencyMeta,
        context: click.Context,
    ) -> dict[str, Any]:
        """Return values mapped to ``meta`` while removing them from ``values``."""

        dep_values: dict[str, Any] = {}
        for name in meta.cli_param_names:
            if name in values:
                dep_values[name] = values.pop(name)
        if meta.context_param_name:
            dep_values[meta.context_param_name] = context
        return dep_values

    def build_default_values(self, callback: Callable[..., Any]) -> dict[str, Any]:
        """Return default parameter values derived from ``callback`` signature."""

        defaults: dict[str, Any] = {}
        signature = inspect.signature(callback)
        for name, parameter in signature.parameters.items():
            default_candidate = parameter.default
            if isinstance(default_candidate, ParameterInfo):
                defaults[name] = getattr(default_candidate, "default", None)
            elif default_candidate is inspect.Signature.empty:
                defaults[name] = None
            else:
                defaults[name] = default_candidate
        return defaults

    def _process_parameter(
        self,
        *,
        param_name: str,
        parameter: inspect.Parameter,
        type_hints: dict[str, Any],
        state: _AnalysisState,
    ) -> None:
        """Analyse a single parameter and update analysis state."""

        annotation = type_hints.get(param_name, parameter.annotation)
        annotation, parameter_info, dependency_info = self._parse_annotation(annotation, parameter)

        if self._is_context_parameter(annotation):
            if state.context_param_name is None:
                state.context_param_name = param_name
            return

        if dependency_info is not None:
            self._add_dependency_parameter(
                param_name=param_name,
                dependency_callable=dependency_info.dependency,
                state=state,
            )
            return

        self._add_direct_parameter(
            param_name=param_name,
            context=_DirectParameterContext(
                parameter=parameter,
                annotation=annotation,
                parameter_info=parameter_info,
            ),
            state=state,
        )

    def _add_dependency_parameter(
        self,
        *,
        param_name: str,
        dependency_callable: Callable[..., Any],
        state: _AnalysisState,
    ) -> None:
        """Register dependency metadata for ``param_name``."""

        dep_analysis = self.analyze(dependency_callable)
        state.params.extend(dep_analysis.params)
        state.convertors.update(dep_analysis.convertors)
        state.dependencies.append(
            _DependencyMeta(
                param_name=param_name,
                dependency=dependency_callable,
                cli_param_names=set(dep_analysis.cli_param_names),
                context_param_name=dep_analysis.context_param_name,
            )
        )
        state.cli_param_names.update(dep_analysis.cli_param_names)

    def _add_direct_parameter(
        self,
        *,
        param_name: str,
        context: _DirectParameterContext,
        state: _AnalysisState,
    ) -> None:
        """Register a direct CLI parameter without dependencies.

        Args:
            param_name: Name of the CLI parameter.
            context: Metadata describing the Typer parameter declaration.
            state: Accumulated analysis state for the callback.

        """

        click_param, convertor = self._build_click_parameter(
            context.parameter,
            context.annotation,
            context.parameter_info,
        )
        state.params.append(click_param)
        if convertor:
            state.convertors[param_name] = convertor
        state.cli_param_names.add(param_name)


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
        """

        argument_records: list[tuple[str, str]] = []
        option_entries: list[tuple[tuple[str, int], tuple[str, str]]] = []

        for index, param in enumerate(self.get_params(ctx)):
            record = param.get_help_record(ctx)
            if record is None:
                continue
            if getattr(param, "param_type_name", "") == ARGUMENT_PARAM_TYPE:
                argument_records.append(record)
                continue
            option_entries.append(((_primary_option_name(param), index), record))

        if argument_records:
            with formatter.section("Arguments"):
                formatter.write_dl(argument_records)

        if option_entries:
            sorted_entries = sorted(option_entries, key=lambda item: item[0])
            sorted_records = [entry for _, entry in sorted_entries]
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
