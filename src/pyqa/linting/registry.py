# SPDX-License-Identifier: MIT
"""Registry describing the internal linters available to the CLI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from collections.abc import Callable

from pyqa.cli.commands.lint.preparation import PreparedLintState
from pyqa.config import Config
from pyqa.core.models import ToolOutcome
from pyqa.tools.base import DeferredCommand, Tool, ToolAction, ToolContext
from pyqa.tools.registry import ToolRegistry

from .base import InternalLintReport, InternalLintRunner
from .cache_usage import run_cache_linter
from .closures import run_closure_linter
from .docstrings import run_docstring_linter
from .quality import run_quality_linter
from .signatures import run_signature_linter
from .suppressions import run_suppression_linter
from .typing_strict import run_typing_linter


@dataclass(slots=True)
class InternalLinterDefinition:
    """Describe how a CLI meta flag maps to an internal linter."""

    name: str
    meta_attribute: str | None
    selection_tokens: tuple[str, ...]
    runner: InternalLintRunner
    description: str
    phase: str = "lint"
    tags: tuple[str, ...] = ("internal-linter",)
    default_enabled: bool = False
    requires_config: bool = False


INTERNAL_LINTERS: tuple[InternalLinterDefinition, ...] = (
    InternalLinterDefinition(
        name="docstrings",
        meta_attribute="check_docstrings",
        selection_tokens=("docstring", "docstrings"),
        runner=run_docstring_linter,
        description="Validate Google-style docstrings using Tree-sitter and spaCy.",
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
        name="quality",
        meta_attribute=None,
        selection_tokens=("quality", "license"),
        runner=run_quality_linter,
        description="Enforce license compliance and structural quality checks.",
        phase="utility",
        tags=("internal-linter", "quality"),
        default_enabled=True,
        requires_config=True,
    ),
)


def iter_internal_linters() -> Sequence[InternalLinterDefinition]:
    """Return the registered internal lint definitions."""

    return INTERNAL_LINTERS


def ensure_internal_tools_registered(
    *,
    registry: ToolRegistry,
    state: PreparedLintState,
    config: Config,
) -> None:
    """Register internal linter tools with ``registry`` when absent."""

    for definition in INTERNAL_LINTERS:
        if registry.try_get(definition.name) is not None:
            continue
        runner = definition.runner
        if definition.requires_config:
            runner = partial(runner, config=config)
        tool = _build_internal_tool(
            definition=definition,
            state=state,
            runner=runner,
        )
        registry.register(tool)


def _build_internal_tool(
    *,
    definition: InternalLinterDefinition,
    state: PreparedLintState,
    runner: InternalLintRunner,
) -> Tool:
    """Return a :class:`Tool` that executes the provided internal runner."""

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
        phase=definition.phase,
        before=(),
        after=(),
        languages=(),
        file_extensions=(),
        config_files=(),
        description=definition.description,
        tags=definition.tags,
        auto_install=False,
        default_enabled=definition.default_enabled,
    )


def configure_internal_tool_defaults(*, registry: ToolRegistry, state: PreparedLintState) -> None:
    """Toggle default-enabled flags for internal tools based on CLI meta."""

    for definition in INTERNAL_LINTERS:
        tool = registry.try_get(definition.name)
        if tool is None:
            continue
        enable = definition.default_enabled
        if getattr(state.meta, "normal", False):
            enable = True
        tool.default_enabled = enable


def _wrap_internal_runner(
    definition: InternalLinterDefinition,
    state: PreparedLintState,
    runner: InternalLintRunner,
) -> Callable[[ToolContext], ToolOutcome]:
    """Return an action runner compatible with :class:`ToolAction`."""

    def _execute(context: ToolContext) -> ToolOutcome:
        report: InternalLintReport = runner(state, emit_to_logger=False)
        outcome = report.outcome.model_copy(deep=True)
        outcome.tool = definition.name
        outcome.action = "check"
        return outcome

    return _execute


__all__ = [
    "InternalLinterDefinition",
    "INTERNAL_LINTERS",
    "iter_internal_linters",
    "ensure_internal_tools_registered",
    "configure_internal_tool_defaults",
]
