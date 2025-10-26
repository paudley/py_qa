# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Registry describing the internal linters available to the CLI."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Protocol, cast

from pyqa.config import Config
from pyqa.core.models import ToolOutcome
from pyqa.platform.workspace import is_py_qa_workspace
from pyqa.tools.base import (
    DeferredCommand,
    InternalActionRunner,
    PhaseLiteral,
    Tool,
    ToolAction,
    ToolContext,
)
from pyqa.tools.registry import ToolRegistry

from .base import InternalLintReport, InternalLintRunner, as_internal_runner
from .cache_usage import run_cache_linter
from .closures import run_closure_linter
from .di import run_pyqa_di_linter
from .docstrings import run_docstring_linter
from .generic_value_types import run_generic_value_type_linter
from .interfaces import run_pyqa_interface_linter
from .missing import run_missing_linter
from .module_docs import run_pyqa_module_doc_linter
from .quality import (
    run_copyright_linter,
    run_file_size_linter,
    run_license_header_linter,
    run_pyqa_python_hygiene_linter,
    run_pyqa_schema_sync_linter,
    run_python_hygiene_linter,
)
from .signatures import run_signature_linter
from .suppressions import run_suppression_linter
from .typing_strict import run_typing_linter
from .value_types import run_value_type_linter

class _PreparedLintStateProtocol(Protocol):
    """Runtime placeholder for the lint state protocol used during registration."""

    # Protocol intentionally empty; registry logic treats lint state as opaque.
    pass


if TYPE_CHECKING:
    from pyqa.interfaces.linting import PreparedLintState
else:
    PreparedLintState = _PreparedLintStateProtocol

_TEST_SUPPRESSION_SUFFIX = r"(?:.+/)?tests?/.*$"


@dataclass(slots=True)
class InternalLinterOptions:
    """Describe execution-time options for an internal linter."""

    phase: PhaseLiteral = "lint"
    tags: tuple[str, ...] = ("internal-linter",)
    default_enabled: bool = False
    requires_config: bool = False
    pyqa_default_enabled: bool = False


@dataclass(slots=True)
class InternalLinterDefinition:
    """Describe how a CLI meta flag maps to an internal linter."""

    name: str
    meta_attribute: str | None
    selection_tokens: tuple[str, ...]
    runner: Callable[..., InternalLintReport]
    description: str
    options: InternalLinterOptions = field(default_factory=InternalLinterOptions)
    pyqa_scoped: bool = False


@dataclass(slots=True)
class _InternalRunnerAction:
    """Invoke an internal linter runner and normalise the resulting outcome."""

    definition: InternalLinterDefinition
    state: PreparedLintState
    runner: InternalLintRunner

    def __call__(self, _context: ToolContext) -> ToolOutcome:
        """Execute the bound runner and annotate the resulting outcome.

        Args:
            _context: Tool context provided by orchestrator execution.

        Returns:
            ToolOutcome: Deep-copied outcome associated with ``definition``.
        """

        report: InternalLintReport = self.runner(self.state, emit_to_logger=False)
        outcome = report.outcome.model_copy(deep=True)
        outcome.tool = self.definition.name
        outcome.action = "check"
        return outcome


@dataclass(slots=True)
class _RunnerBinding:
    """Standardise runner call signatures for registration helpers."""

    func: Callable[..., InternalLintReport]

    def __call__(self, state: PreparedLintState, emit_to_logger: bool) -> InternalLintReport:
        """Delegate to ``func`` using the canonical internal runner signature.

        Args:
            state: Prepared lint state provided by the CLI pipeline.
            emit_to_logger: Flag indicating whether logging side effects should occur.

        Returns:
            InternalLintReport: Report produced by ``func``.
        """

        return self.func(state, emit_to_logger=emit_to_logger)


INTERNAL_LINTERS: tuple[InternalLinterDefinition, ...] = (
    InternalLinterDefinition(
        name="docstrings",
        meta_attribute="check_docstrings",
        selection_tokens=("docstring", "docstrings"),
        runner=run_docstring_linter,
        description="Validate Google-style docstrings using Tree-sitter and spaCy.",
    ),
    InternalLinterDefinition(
        name="pyqa-interfaces",
        meta_attribute="check_interfaces",
        selection_tokens=("pyqa-interfaces", "interfaces", "pyqa-interface"),
        runner=run_pyqa_interface_linter,
        description="Ensure imports target pyqa.interfaces.* and ban concrete DI construction.",
        options=InternalLinterOptions(tags=("internal-linter", "internal-pyqa")),
        pyqa_scoped=True,
    ),
    InternalLinterDefinition(
        name="pyqa-di",
        meta_attribute="check_di",
        selection_tokens=("pyqa-di", "di", "pyqa-composition"),
        runner=run_pyqa_di_linter,
        description="Flag service registration outside approved composition roots.",
        options=InternalLinterOptions(tags=("internal-linter", "internal-pyqa")),
        pyqa_scoped=True,
    ),
    InternalLinterDefinition(
        name="pyqa-module-docs",
        meta_attribute="check_module_docs",
        selection_tokens=("pyqa-module-docs", "module-docs"),
        runner=run_pyqa_module_doc_linter,
        description="Require package-level MODULE.md documentation with standard sections.",
        options=InternalLinterOptions(tags=("internal-linter", "internal-pyqa")),
        pyqa_scoped=True,
    ),
    InternalLinterDefinition(
        name="pyqa-python-hygiene",
        meta_attribute="check_pyqa_python_hygiene",
        selection_tokens=("pyqa-python-hygiene", "python-hygiene-pyqa"),
        runner=run_pyqa_python_hygiene_linter,
        description="Detect SystemExit and print leaks outside sanctioned pyqa entry points.",
        options=InternalLinterOptions(tags=("internal-linter", "internal-pyqa"), requires_config=True),
        pyqa_scoped=True,
    ),
    InternalLinterDefinition(
        name="suppressions",
        meta_attribute="check_suppressions",
        selection_tokens=("suppressions", "lint-suppressions"),
        runner=run_suppression_linter,
        description="Report discouraged noqa/pylint/mypy suppression directives.",
    ),
    InternalLinterDefinition(
        name="types",
        meta_attribute="check_types_strict",
        selection_tokens=("types", "typing", "strict-types"),
        runner=run_typing_linter,
        description="Detect banned Any/object annotations in code paths.",
    ),
    InternalLinterDefinition(
        name="missing",
        meta_attribute="check_missing",
        selection_tokens=("missing", "todo"),
        runner=run_missing_linter,
        description="Flag TODO markers and other missing implementation placeholders.",
        options=InternalLinterOptions(
            tags=("internal-linter", "missing"),
            pyqa_default_enabled=True,
        ),
    ),
    InternalLinterDefinition(
        name="closures",
        meta_attribute="check_closures",
        selection_tokens=("closures", "partials"),
        runner=run_closure_linter,
        description="Discourage ad-hoc closure factories in favour of functools.partial or itertools helpers.",
    ),
    InternalLinterDefinition(
        name="signatures",
        meta_attribute="check_signatures",
        selection_tokens=("signatures", "parameters"),
        runner=run_signature_linter,
        description="Highlight functions whose signatures exceed the parameter threshold.",
    ),
    InternalLinterDefinition(
        name="cache",
        meta_attribute="check_cache_usage",
        selection_tokens=("cache", "lru_cache", "functools"),
        runner=run_cache_linter,
        description="Reject direct functools.lru_cache usage in favour of pyqa.cache utilities.",
    ),
    InternalLinterDefinition(
        name="pyqa-value-types",
        meta_attribute="check_value_types",
        selection_tokens=("value-types", "dunder"),
        runner=run_value_type_linter,
        description="Ensure pyqa value-type helpers expose ergonomic dunder methods.",
        options=InternalLinterOptions(tags=("internal-linter", "pyqa-only")),
        pyqa_scoped=True,
    ),
    InternalLinterDefinition(
        name="generic-value-types",
        meta_attribute="check_value_types_general",
        selection_tokens=("value-types-general", "generic-value-types"),
        runner=run_generic_value_type_linter,
        description="Recommend dunder methods for value-type classes using Tree-sitter heuristics.",
        options=InternalLinterOptions(requires_config=True),
    ),
    InternalLinterDefinition(
        name="license-header",
        meta_attribute="check_license_header",
        selection_tokens=("license-header", "license-headers"),
        runner=run_license_header_linter,
        description="Validate SPDX license headers across targeted files.",
        options=InternalLinterOptions(
            phase="utility",
            tags=("internal-linter", "quality"),
            requires_config=True,
        ),
    ),
    InternalLinterDefinition(
        name="copyright",
        meta_attribute="check_copyright",
        selection_tokens=("copyright", "copyrights"),
        runner=run_copyright_linter,
        description="Ensure copyright notices stay consistent with repository policy.",
        options=InternalLinterOptions(
            phase="utility",
            tags=("internal-linter", "quality"),
            requires_config=True,
        ),
    ),
    InternalLinterDefinition(
        name="python-hygiene",
        meta_attribute="check_python_hygiene",
        selection_tokens=("python-hygiene", "py-hygiene"),
        runner=run_python_hygiene_linter,
        description="Detect debug breakpoints and bare except clauses in Python code.",
        options=InternalLinterOptions(
            phase="utility",
            tags=("internal-linter", "quality"),
            requires_config=True,
        ),
    ),
    InternalLinterDefinition(
        name="file-size",
        meta_attribute="check_file_size",
        selection_tokens=("file-size", "size"),
        runner=run_file_size_linter,
        description="Flag files that exceed configured size thresholds.",
        options=InternalLinterOptions(
            phase="utility",
            tags=("internal-linter", "quality"),
            requires_config=True,
        ),
    ),
    InternalLinterDefinition(
        name="pyqa-schema-sync",
        meta_attribute="check_schema_sync",
        selection_tokens=("schema-sync", "pyqa-schema"),
        runner=run_pyqa_schema_sync_linter,
        description="Verify pyqa schema documentation matches generated artefacts.",
        options=InternalLinterOptions(
            phase="utility",
            tags=("internal-linter", "internal-pyqa", "quality"),
            requires_config=True,
        ),
        pyqa_scoped=True,
    ),
)


def iter_internal_linters() -> Sequence[InternalLinterDefinition]:
    """Return the registered internal lint definitions.

    Returns:
        Sequence[InternalLinterDefinition]: Immutable collection of definitions.
    """

    return INTERNAL_LINTERS


def ensure_internal_tools_registered(
    *,
    registry: ToolRegistry,
    state: PreparedLintState,
    config: Config,
) -> None:
    """Register internal linter tools with ``registry`` when absent.

    Args:
        registry: Tool registry populated by the CLI.
        state: Prepared lint state supplying CLI metadata.
        config: Effective configuration passed to config-aware linters.
    """

    for definition in INTERNAL_LINTERS:
        if registry.try_get(definition.name) is not None:
            _inject_internal_test_suppression(config, definition.name)
            continue
        runner_callable = definition.runner
        if definition.options.requires_config:
            runner_callable = partial(runner_callable, config=config)
        runner = as_internal_runner(definition.name, _bind_runner_callable(runner_callable))
        tool = _build_internal_tool(
            definition=definition,
            state=state,
            runner=runner,
        )
        registry.register(tool)
        _inject_internal_test_suppression(config, definition.name)


def _inject_internal_test_suppression(config: Config, tool_name: str) -> None:
    """Ensure internal linters suppress diagnostics originating from tests.

    Args:
        config: Effective configuration passed to internal linters.
        tool_name: Name of the internal linter being configured.
    """

    pattern = rf"^{re.escape(tool_name)}, {_TEST_SUPPRESSION_SUFFIX}"
    filters = config.output.tool_filters.setdefault(tool_name, [])
    if pattern not in filters:
        filters.append(pattern)


def _build_internal_tool(
    *,
    definition: InternalLinterDefinition,
    state: PreparedLintState,
    runner: InternalLintRunner,
) -> Tool:
    """Return a :class:`Tool` that executes the provided internal runner.

    Args:
        definition: Internal linter definition describing metadata.
        state: Prepared lint state used for report normalisation.
        runner: Callable responsible for executing the internal linter.

    Returns:
        Tool: Registered tool wrapper around the internal linter runner.
    """

    action_runner = _wrap_internal_runner(definition, state, runner)
    action = ToolAction(
        name="check",
        command=DeferredCommand(()),
        append_files=False,
        internal_runner=action_runner,
        description=definition.description,
        parser=None,
        filter_patterns=(),
    )
    return Tool(
        name=definition.name,
        actions=(action,),
        phase=definition.options.phase,
        before=(),
        after=(),
        languages=(),
        file_extensions=(),
        config_files=(),
        description=definition.description,
        tags=definition.options.tags,
        auto_install=False,
        default_enabled=definition.options.default_enabled,
    )


def configure_internal_tool_defaults(*, registry: ToolRegistry, state: PreparedLintState) -> None:
    """Toggle default-enabled flags for internal tools based on CLI meta.

    Args:
        registry: Tool registry hosting internal linter definitions.
        state: Prepared lint state containing CLI runtime metadata.
    """

    pyqa_scope_active = is_py_qa_workspace(state.root)
    meta_runtime = getattr(state.meta, "runtime", None)
    if meta_runtime is not None and getattr(meta_runtime, "pyqa_rules", False):
        pyqa_scope_active = True
    for definition in INTERNAL_LINTERS:
        tool = registry.try_get(definition.name)
        if tool is None:
            continue
        enable = definition.options.default_enabled
        if definition.options.pyqa_default_enabled and pyqa_scope_active:
            enable = True
        if getattr(state.meta, "normal", False):
            enable = True
        tool.default_enabled = enable


def _wrap_internal_runner(
    definition: InternalLinterDefinition,
    state: PreparedLintState,
    runner: InternalLintRunner,
) -> InternalActionRunner:
    """Return an action runner compatible with :class:`ToolAction`.

    Args:
        definition: Internal linter definition describing the tool.
        state: Prepared lint state providing filesystem context.
        runner: Callable that executes the internal linter logic.

    Returns:
        InternalActionRunner: Adapter bridging the tool action and runner.
    """

    return cast(InternalActionRunner, _InternalRunnerAction(definition=definition, state=state, runner=runner))


def _bind_runner_callable(
    func: Callable[..., InternalLintReport],
) -> Callable[[PreparedLintState, bool], InternalLintReport]:
    """Return a callable enforcing the standard internal runner signature.

    Args:
        func: Internal linter runner requiring prepared state injection.

    Returns:
        Callable[[PreparedLintState, bool], InternalLintReport]: Runner bound to the standard signature.
    """

    return _RunnerBinding(func=func)


__all__ = [
    "InternalLinterOptions",
    "InternalLinterDefinition",
    "INTERNAL_LINTERS",
    "iter_internal_linters",
    "ensure_internal_tools_registered",
    "configure_internal_tool_defaults",
]
