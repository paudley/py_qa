# SPDX-License-Identifier: MIT
"""Interface data structures capturing tool-selection outcomes.

Modules outside ``pyqa.orchestration`` should consume these definitions instead
of depending on the concrete selector implementation so that orchestration can
be evolved without cascading changes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, cast

from pyqa.config import Config, SensitivityLevel
from pyqa.platform.workspace import is_py_qa_workspace
from pyqa.tools.base import PHASE_NAMES, PhaseLiteral

ToolFamilyLiteral = Literal["external", "internal", "internal-pyqa", "unknown"]
DEFAULT_PHASE: Final[PhaseLiteral] = "lint"
PHASE_ORDER: Final[tuple[PhaseLiteral, ...]] = cast(tuple[PhaseLiteral, ...], PHASE_NAMES)


@dataclass(frozen=True, slots=True)
class SelectionContext:
    """Derived inputs used to evaluate tool eligibility."""

    config: Config
    root: Path
    files: tuple[Path, ...]
    requested_only: tuple[str, ...]
    requested_languages: tuple[str, ...]
    detected_languages: tuple[str, ...]
    file_extensions: frozenset[str]
    sensitivity: SensitivityLevel
    pyqa_workspace: bool
    pyqa_rules: bool

    @property
    def language_scope(self) -> frozenset[str]:
        """Return languages that should guide tool selection heuristics."""

        if self.requested_languages:
            return frozenset(self.requested_languages)
        return frozenset(self.detected_languages)


@dataclass(frozen=True, slots=True)
class ToolEligibility:
    """Per-tool predicate evaluation used to explain selection decisions."""

    name: str
    family: ToolFamilyLiteral
    phase: str
    available: bool = True
    requested_via_only: bool = False
    language_match: bool | None = None
    extension_match: bool | None = None
    config_match: bool | None = None
    sensitivity_ok: bool | None = None
    pyqa_scope: bool | None = None
    default_enabled: bool | None = None


@dataclass(frozen=True, slots=True)
class ToolDecision:
    """Final verdict for an individual tool."""

    name: str
    family: ToolFamilyLiteral
    phase: str
    action: Literal["run", "skip"]
    reasons: tuple[str, ...]
    eligibility: ToolEligibility


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """Outcome of planning a lint run given current configuration."""

    ordered: tuple[str, ...]
    decisions: tuple[ToolDecision, ...]
    context: SelectionContext

    @property
    def run_names(self) -> tuple[str, ...]:
        """Return tool names scheduled for execution."""

        return self.ordered

    @property
    def run_decisions(self) -> tuple[ToolDecision, ...]:
        """Return decisions corresponding to scheduled tools in run order."""

        sequence = {name: index for index, name in enumerate(self.ordered)}
        filtered = [decision for decision in self.decisions if decision.action == "run" and decision.name in sequence]
        filtered.sort(key=lambda decision: sequence[decision.name])
        return tuple(filtered)


class UnknownToolRequestedError(RuntimeError):
    """Error raised when ``--only`` references tools that are not registered."""

    def __init__(self, tool_names: Sequence[str]) -> None:
        deduplicated = tuple(dict.fromkeys(tool_names))
        display = ", ".join(deduplicated)
        message = f"Unknown tool(s) requested via --only: {display}"
        super().__init__(message)
        self.tool_names: tuple[str, ...] = deduplicated


def build_selection_context(
    cfg: Config,
    files: Sequence[Path],
    *,
    detected_languages: Sequence[str],
    root: Path,
) -> SelectionContext:
    """Return a :class:`SelectionContext` derived from ``cfg`` and ``files``."""

    file_tuple = tuple(files)
    extensions = frozenset(path.suffix.lower() for path in file_tuple if path.suffix)
    return SelectionContext(
        config=cfg,
        root=root,
        files=file_tuple,
        requested_only=tuple(cfg.execution.only),
        requested_languages=tuple(cfg.execution.languages),
        detected_languages=tuple(sorted(detected_languages)),
        file_extensions=extensions,
        sensitivity=cfg.severity.sensitivity,
        pyqa_workspace=is_py_qa_workspace(root),
        pyqa_rules=cfg.execution.pyqa_rules,
    )


__all__ = [
    "PHASE_ORDER",
    "PhaseLiteral",
    "DEFAULT_PHASE",
    "SelectionContext",
    "SelectionResult",
    "ToolDecision",
    "ToolEligibility",
    "ToolFamilyLiteral",
    "UnknownToolRequestedError",
    "build_selection_context",
]
