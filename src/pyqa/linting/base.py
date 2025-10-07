# SPDX-License-Identifier: MIT
"""Shared primitives for internal linters shipped with pyqa."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pyqa.core.models import ToolOutcome


@dataclass(slots=True)
class InternalLintReport:
    """Represent the outcome and file footprint of an internal lint run."""

    outcome: ToolOutcome
    files: tuple[Path, ...]


class InternalLintRunner(Protocol):
    """Protocol describing reusable internal linter callables."""

    def __call__(
        self, state: PreparedLintState, *, emit_to_logger: bool
    ) -> InternalLintReport:  # pragma: no cover - structural contract
        """Execute the linter using CLI-prepared state."""


if False:  # pragma: no cover - import guard for type checking
    from pyqa.cli.commands.lint.preparation import PreparedLintState


__all__ = ["InternalLintReport", "InternalLintRunner"]
