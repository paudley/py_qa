# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Render refactor navigator panels for concise output."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from rich import box
from rich.panel import Panel
from rich.table import Table

from pyqa.runtime.console.manager import get_console_manager

from ...config import OutputConfig
from ...core.models import JsonValue, RunResult
from ...core.serialization import coerce_optional_int, coerce_optional_str, safe_int


@dataclass(slots=True)
class _RefactorNavigationEntry:
    """Structured view of a refactor navigator entry."""

    location: str
    issue_count: int
    tags: tuple[str, ...]
    size: int | None
    complexity: int | None

    @classmethod
    def from_payload(cls, payload: Mapping[str, JsonValue]) -> _RefactorNavigationEntry | None:
        """Return an entry parsed from ``payload`` when valid.

        Args:
            payload: Mapping containing refactor navigator fields.

        Returns:
            _RefactorNavigationEntry | None: Parsed entry or ``None`` when the payload lacks
            required fields.
        """

        function_name = coerce_optional_str(payload.get("function")) or "<module>"
        file_path = coerce_optional_str(payload.get("file"))
        location = f"{file_path}:{function_name}" if file_path else function_name
        issue_tags = _extract_issue_tags(payload.get("issue_tags"))
        issue_count = sum(issue_tags.values())
        tags = tuple(sorted(issue_tags))
        size = coerce_optional_int(payload.get("size"))
        complexity = coerce_optional_int(payload.get("complexity"))
        return cls(
            location=location,
            issue_count=issue_count,
            tags=tags,
            size=size,
            complexity=complexity,
        )


def _extract_issue_tags(raw: JsonValue | None) -> dict[str, int]:
    """Return issue tag counts from ``raw`` ensuring integer values.

    Args:
        raw: JSON value expected to contain a mapping of issue tag names to counts.

    Returns:
        dict[str, int]: Normalised tag counts keyed by tag identifier.
    """

    if not isinstance(raw, Mapping):
        return {}
    tags: dict[str, int] = {}
    for key, value in raw.items():
        tags[key] = safe_int(value, default=0)
    return tags


def _iter_refactor_payload(value: JsonValue | None) -> Iterable[Mapping[str, JsonValue]]:
    """Yield mapping payloads from ``value`` suitable for navigation entries.

    Args:
        value: JSON payload retrieved from analysis metadata.

    Yields:
        Mapping[str, JsonValue]: Candidate entries ready for conversion into
        structured navigator rows.
    """

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for entry in value[:5]:
            if isinstance(entry, Mapping):
                yield entry


def render_refactor_navigator(result: RunResult, cfg: OutputConfig) -> None:
    """Render the refactor navigator panel when analysis data is available.

    Args:
        result: Completed run result containing analysis metadata.
        cfg: Output configuration describing formatting preferences.
    """

    entries = [
        parsed
        for payload in _iter_refactor_payload(result.analysis.get("refactor_navigator"))
        if (parsed := _RefactorNavigationEntry.from_payload(payload)) is not None
    ]
    if not entries:
        return

    console = get_console_manager().get(color=cfg.color, emoji=cfg.emoji)
    table = Table(box=box.SIMPLE_HEAVY if cfg.color else box.SIMPLE)
    table.add_column("Function", overflow="fold")
    table.add_column("Issues", justify="right")
    table.add_column("Tags", overflow="fold")
    table.add_column("Size", justify="right")
    table.add_column("Complexity", justify="right")

    for entry in entries:
        table.add_row(
            entry.location,
            str(entry.issue_count),
            ", ".join(entry.tags) or "-",
            "-" if entry.size is None else str(entry.size),
            "-" if entry.complexity is None else str(entry.complexity),
        )

    panel = Panel(
        table,
        title="Refactor Navigator",
        border_style="magenta" if cfg.color else "none",
    )
    console.print(panel)


__all__ = ["render_refactor_navigator"]
