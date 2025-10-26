# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared primitives for internal linters shipped with pyqa."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pyqa.core.models import Diagnostic, ToolExitCategory, ToolOutcome


class _PreparedLintStateProtocol(Protocol):
    """Runtime placeholder for the prepared lint state protocol."""

    # The protocol intentionally omits members; runtime code treats it as opaque.
    pass


if TYPE_CHECKING:
    from pyqa.interfaces.linting import PreparedLintState
else:
    PreparedLintState = _PreparedLintStateProtocol


@dataclass(slots=True)
class InternalLintReport:
    """Represent the outcome and file footprint of an internal lint run."""

    outcome: ToolOutcome
    files: tuple[Path, ...]


RunnerCallable = Callable[[PreparedLintState, bool], InternalLintReport]


class InternalLintRunner(ABC):
    """Abstract base class describing reusable internal linter callables."""

    def __init__(self, runner_name: str) -> None:
        """Store the human-readable name for the runner.

        Args:
            runner_name: Identifier exposed for diagnostics and logging.
        """

        self._runner_name = runner_name

    @property
    def runner_name(self) -> str:
        """Return a human-readable name for the linter.

        Returns:
            str: Configured runner name.
        """

        return self._runner_name

    @abstractmethod
    def run(
        self,
        state: PreparedLintState,
        *,
        emit_to_logger: bool,
    ) -> InternalLintReport:
        """Execute the linter using CLI-prepared state.

        Args:
            state: Prepared lint state describing the workspace context.
            emit_to_logger: Flag indicating whether logging output should be produced.

        Returns:
            InternalLintReport: Result produced by the internal runner.
        """

    def __call__(
        self,
        state: PreparedLintState,
        *,
        emit_to_logger: bool,
    ) -> InternalLintReport:
        """Execute the linter using CLI-prepared state.

        Args:
            state: Prepared lint state describing the workspace context.
            emit_to_logger: Flag indicating whether logging output should be produced.

        Returns:
            InternalLintReport: Result produced by the internal runner.
        """

        return self.run(state, emit_to_logger=emit_to_logger)


__all__ = ["InternalLintReport", "InternalLintRunner"]


class _CallableInternalRunner(InternalLintRunner):
    """Concrete internal runner with an explicit name binding."""

    __slots__ = ("_runner_name", "_func")

    def __init__(
        self,
        *,
        name: str,
        func: Callable[[PreparedLintState, bool], InternalLintReport],
    ) -> None:
        """Create a callable runner delegating to ``func``.

        Args:
            name: Human-readable runner identifier.
            func: Callable implementing the lint logic.
        """

        super().__init__(name)
        self._func = func

    def run(self, state: PreparedLintState, *, emit_to_logger: bool) -> InternalLintReport:
        """Execute the wrapped callable and return its report.

        Args:
            state: Prepared lint state provided by the CLI pipeline.
            emit_to_logger: Flag indicating whether logging output should be produced.

        Returns:
            InternalLintReport: Report returned by the wrapped callable.
        """

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

    return _CallableInternalRunner(name=name, func=func)


__all__.append("as_internal_runner")


def build_internal_report(
    *,
    tool: str,
    stdout: Sequence[str],
    diagnostics: Sequence[Diagnostic],
    files: Sequence[Path],
) -> InternalLintReport:
    """Return an internal lint report with a normalised outcome.

    Args:
        tool: Identifier of the linter that produced the diagnostics.
        stdout: Lines emitted during execution.
        diagnostics: Diagnostics raised by the linter.
        files: Files inspected during the lint run.

    Returns:
        InternalLintReport: Aggregated outcome and file footprint.
    """

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
