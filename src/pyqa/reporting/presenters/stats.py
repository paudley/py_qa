# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Rich panel rendering for lint statistics."""

from __future__ import annotations

from dataclasses import dataclass

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pyqa.runtime.console.manager import get_console_manager

from ...config import OutputConfig
from ...core.metrics import SUPPRESSION_LABELS, FileMetrics, compute_file_metrics
from ...core.models import RunResult
from ...filesystem.paths import normalize_path_key


@dataclass(slots=True)
class ActionSummary:
    """Summarise orchestrator action execution outcomes."""

    total: int
    failed: int
    cached: int


@dataclass(slots=True)
class StatsSnapshot:
    """Aggregated metrics displayed in the stats panel."""

    files_count: int
    loc_count: int
    suppression_counts: dict[str, int]
    warnings_per_loc: float
    diagnostics_count: int
    actions: ActionSummary


def emit_stats_panel(result: RunResult, cfg: OutputConfig, diagnostics_count: int) -> None:
    """Render the statistics panel when stats output is enabled.

    Args:
        result: Completed run result containing file metrics.
        cfg: Output configuration describing formatting preferences.
        diagnostics_count: Number of diagnostics emitted during rendering.
    """

    if not cfg.show_stats:
        return
    snapshot = compute_stats_snapshot(result, diagnostics_count)
    console = get_console_manager().get(color=cfg.color, emoji=cfg.emoji)
    panel = create_stats_panel(snapshot, cfg)
    console.print(panel)


def compute_stats_snapshot(result: RunResult, diagnostics_count: int) -> StatsSnapshot:
    """Collect metrics required to render the statistics panel.

    Args:
        result: Completed run result containing per-file metrics.
        diagnostics_count: Number of diagnostics emitted during rendering.

    Returns:
        StatsSnapshot: Aggregated metrics describing run statistics.
    """

    metrics = _gather_metrics(result)
    loc_count = sum(metric.line_count for metric in metrics.values())
    suppression_counts = {
        label: sum(metric.suppressions.get(label, 0) for metric in metrics.values()) for label in SUPPRESSION_LABELS
    }
    warnings_per_loc = diagnostics_count / loc_count if loc_count else 0.0
    outcomes = result.outcomes
    extra_failures = int(result.analysis.get("aux_tool_failures", 0))
    actions = ActionSummary(
        total=len(outcomes),
        failed=sum(1 for outcome in outcomes if outcome.indicates_failure()) + extra_failures,
        cached=sum(1 for outcome in outcomes if outcome.cached),
    )
    return StatsSnapshot(
        files_count=len(result.files),
        loc_count=loc_count,
        suppression_counts=suppression_counts,
        warnings_per_loc=warnings_per_loc,
        diagnostics_count=diagnostics_count,
        actions=actions,
    )


def create_stats_panel(snapshot: StatsSnapshot, cfg: OutputConfig) -> Panel:
    """Create a Rich panel displaying lint statistics.

    Args:
        snapshot: Aggregated statistics for the current run.
        cfg: Output configuration describing formatting preferences.

    Returns:
        Panel: Rich panel containing formatted statistics.
    """

    table = Table(
        show_header=False,
        box=box.SIMPLE,
        pad_edge=False,
        expand=False,
    )
    label_style = "yellow" if cfg.color else None
    value_style = "orange1" if cfg.color else None

    def styled(value: str, style: str | None) -> Text:
        """Return a Rich text entry styled when necessary."""

        return Text(value, style=style) if style else Text(value)

    table.add_column(style=label_style, justify="left", no_wrap=True)
    table.add_column(style=value_style, justify="right", no_wrap=True)

    table.add_row(styled("Files", label_style), styled(f"{snapshot.files_count}", value_style))
    table.add_row(
        styled("Lines of code", label_style),
        styled(f"{snapshot.loc_count:,}", value_style),
    )
    table.add_row(
        styled("Actions", label_style),
        styled(str(snapshot.actions.total), value_style),
    )
    table.add_row(
        styled("- cached", label_style),
        styled(str(snapshot.actions.cached), value_style),
    )
    table.add_row(
        styled("- failed", label_style),
        styled(str(snapshot.actions.failed), value_style),
    )
    total_suppressions = sum(snapshot.suppression_counts.values())
    table.add_row(
        styled("Lint suppressions", label_style),
        styled(str(total_suppressions), value_style),
    )
    for label in SUPPRESSION_LABELS:
        table.add_row(
            styled(f"- {label} suppressions", label_style),
            styled(str(snapshot.suppression_counts[label]), value_style),
        )
    table.add_row(
        styled("Warnings / LoC", label_style),
        styled(f"{snapshot.warnings_per_loc:.3f}", value_style),
    )

    title_text = "stats"
    if cfg.emoji:
        title_text = f"📊 {title_text}"
    title = title_text if not cfg.color else f"[yellow]{title_text}[/yellow]"
    panel = Panel.fit(
        table,
        title=title,
        padding=(0, 1),
    )
    if cfg.color:
        panel.border_style = "yellow"
    return panel


def _gather_metrics(result: RunResult) -> dict[str, FileMetrics]:
    """Gather file metrics needed for statistics rendering.

    Args:
        result: Completed run result containing recorded file metrics.

    Returns:
        dict[str, FileMetrics]: Mapping of normalised file keys to metrics.
    """

    metrics: dict[str, FileMetrics] = {}
    seen: set[str] = set()
    for candidate in result.files:
        key = normalize_path_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        metric = result.file_metrics.get(key)
        if metric is None:
            metric = compute_file_metrics(candidate)
        metric.ensure_labels()
        metrics[key] = metric
    return metrics


__all__ = [
    "StatsSnapshot",
    "emit_stats_panel",
    "compute_stats_snapshot",
    "create_stats_panel",
]
