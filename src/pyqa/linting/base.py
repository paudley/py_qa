# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared primitives for internal linters shipped with pyqa."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pyqa.core.models import Diagnostic, ToolExitCategory, ToolOutcome


@dataclass(slots=True)
class InternalLintReport:
    """Represent the outcome and file footprint of an internal lint run."""

    outcome: ToolOutcome
    files: tuple[Path, ...]


class InternalLintRunner(Protocol):
    """Protocol describing reusable internal linter callables."""

    @property
    def runner_name(self) -> str:
        """Return a human-readable name for the linter."""

        raise NotImplementedError

    def __call__(
        self, state: PreparedLintState, *, emit_to_logger: bool
    ) -> InternalLintReport:  # pragma: no cover - structural contract
        """Execute the linter using CLI-prepared state."""

        raise NotImplementedError


if TYPE_CHECKING:  # pragma: no cover - import guard for type checking
    from pyqa.cli.commands.lint.preparation import PreparedLintState


__all__ = ["InternalLintReport", "InternalLintRunner"]


class _CallableInternalRunner(InternalLintRunner):
    """Concrete internal runner with an explicit name binding."""

    def __init__(
        self,
        *,
        runner_name: str,
        func: Callable[[PreparedLintState, bool], InternalLintReport],
    ) -> None:
        self._runner_name = runner_name
        self._func = func

    @property
    def runner_name(self) -> str:
        return self._runner_name

    def __call__(self, state: PreparedLintState, *, emit_to_logger: bool) -> InternalLintReport:
        return self._func(state, emit_to_logger)


def as_internal_runner(
    name: str,
    func: Callable[[PreparedLintState, bool], InternalLintReport],
) -> InternalLintRunner:
    """Return a named internal runner wrapping ``func``.

    Args:
        name: Unique runner identifier.
        func: Callable implementing the linting behaviour.

    Returns:
        InternalLintRunner: Wrapper exposing ``runner_name`` metadata while
        delegating execution to ``func``.
    """

    return _CallableInternalRunner(runner_name=name, func=func)


__all__.append("as_internal_runner")


def build_internal_report(
    *,
    tool: str,
    stdout: Sequence[str],
    diagnostics: Sequence[Diagnostic],
    files: Sequence[Path],
) -> InternalLintReport:
    """Return an internal lint report with a normalised outcome."""

    exit_category = ToolExitCategory.DIAGNOSTIC if diagnostics else ToolExitCategory.SUCCESS
    outcome = ToolOutcome(
        tool=tool,
        action="check",
        returncode=1 if diagnostics else 0,
        stdout=list(stdout),
        stderr=[],
        diagnostics=list(diagnostics),
        exit_category=exit_category,
    )
    return InternalLintReport(outcome=outcome, files=tuple(files))


__all__.append("build_internal_report")
