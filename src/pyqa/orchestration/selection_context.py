# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime helpers for constructing orchestration selection contexts."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final, cast

from pyqa.interfaces.config import Config as ConfigProtocol
from pyqa.interfaces.orchestration_selection import (
    PhaseLiteral,
    SelectionContext,
)
from pyqa.platform.workspace import is_py_qa_workspace
from pyqa.tools.base import PHASE_NAMES

DEFAULT_PHASE: Final[PhaseLiteral] = "lint"
PHASE_ORDER: Final[tuple[PhaseLiteral, ...]] = cast(tuple[PhaseLiteral, ...], tuple(PHASE_NAMES))


class UnknownToolRequestedError(RuntimeError):
    """Raised when ``--only`` specifies tools that are not registered."""

    def __init__(self, tool_names: Sequence[str]) -> None:
        """Create the error with the unresolved tool names.

        Args:
            tool_names: Sequence of tool identifiers requested via ``--only``.
        """

        deduplicated = tuple(dict.fromkeys(tool_names))
        message = f"Unknown tool(s) requested via --only: {', '.join(deduplicated)}"
        super().__init__(message)
        self.tool_names: tuple[str, ...] = deduplicated


def build_selection_context(
    cfg: ConfigProtocol,
    files: Sequence[Path],
    *,
    detected_languages: Sequence[str],
    root: Path,
) -> SelectionContext:
    """Return a :class:`SelectionContext` derived from configuration inputs.

    Args:
        cfg: Effective configuration for the current invocation.
        files: Files discovered for the current run.
        detected_languages: Languages inferred from file contents and paths.
        root: Repository root path used for resolving discovery heuristics.

    Returns:
        SelectionContext: Immutable context describing the orchestration inputs.
    """

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
    "DEFAULT_PHASE",
    "PHASE_ORDER",
    "UnknownToolRequestedError",
    "build_selection_context",
]
