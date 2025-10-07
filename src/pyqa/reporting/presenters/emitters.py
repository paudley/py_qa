# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Emit machine-readable reports for orchestrator results."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from pyqa.core.severity import Severity, severity_to_sarif

from ...analysis.annotations import HighlightKind
from ...core.models import Diagnostic, RunResult
from ...core.serialization import serialize_outcome
from ...interfaces.analysis import AnnotationProvider
from ...utils.bool_utils import interpret_optional_bool
from ..advice.builder import AdviceBuilder, AdviceEntry

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0.json"


@dataclass(slots=True)
class _AdviceProviderContext:
    """Hold mutable advice builder state without relying on globals."""

    builder: AdviceBuilder

    @property
    def annotation_engine(self) -> AnnotationProvider:
        """Return the active annotation provider used by the builder."""

        return self.builder.annotation_engine

    def replace(self, provider: AnnotationProvider) -> None:
        """Replace the underlying advice builder using ``provider``.

        Args:
            provider: Annotation provider injected into the new builder.
        """

        self.builder = AdviceBuilder(annotation_engine=provider)


_ADVICE_PROVIDER_CONTEXT = _AdviceProviderContext(builder=AdviceBuilder())
SEVERITY_ORDER: Final[dict[Severity, int]] = {
    Severity.ERROR: 0,
    Severity.WARNING: 1,
    Severity.NOTICE: 2,
    Severity.NOTE: 3,
}
UNKNOWN_SEVERITY_RANK: Final[int] = 99
ADVICE_PLACEHOLDER: Final[str] = "{advice"
HIGHLIGHT_PLACEHOLDER: Final[str] = "{highlighted_message"


@dataclass(frozen=True)
class HighlightWrapper:
    """Represent Markdown wrappers applied to highlighted spans."""

    prefix: str
    suffix: str


_HIGHLIGHT_WRAPPERS: Final[dict[HighlightKind, HighlightWrapper]] = {
    "function": HighlightWrapper(prefix="**`", suffix="`**"),
    "class": HighlightWrapper(prefix="**`", suffix="`**"),
    "argument": HighlightWrapper(prefix="`", suffix="`"),
    "variable": HighlightWrapper(prefix="`", suffix="`"),
    "attribute": HighlightWrapper(prefix="`", suffix="`"),
    "file": HighlightWrapper(prefix="`", suffix="`"),
}
_DEFAULT_HIGHLIGHT_KIND: Final[HighlightKind] = "argument"
_DEFAULT_HIGHLIGHT_WRAPPER: Final[HighlightWrapper] = HighlightWrapper(prefix="`", suffix="`")


@dataclass(slots=True)
class PRSummaryOptions:
    """User-configurable options for PR summary rendering."""

    limit: int = 100
    min_severity: str = "warning"
    template: str = "- **{severity}** `{tool}` {message} ({location})"
    include_advice: bool = False
    advice_limit: int = 5
    advice_template: str = "- **{category}:** {body}"
    advice_section_builder: Callable[[Sequence[AdviceEntry]], Sequence[str]] | None = None


@dataclass(slots=True)
class _AdviceOptions:
    include: bool
    limit: int
    template: str
    section_builder: Callable[[Sequence[AdviceEntry]], Sequence[str]] | None
    needs_metadata: bool


@dataclass(slots=True)
class _SummaryConfig:
    """Configuration driving PR summary rendering."""

    limit: int
    min_rank: int
    template: str
    needs_highlight: bool
    advice: _AdviceOptions


@dataclass(slots=True)
class _SummaryEntry:
    """Diagnostic data prepared for PR summary rendering."""

    diagnostic: Diagnostic
    tool: str
    location: str
    message: str
    highlighted_message: str


@dataclass(slots=True)
class _AdviceContext:
    """Aggregated advice metadata for PR summaries."""

    entries: list[AdviceEntry]
    summary: str
    primary_body: str
    primary_category: str
    count: int


def _coerce_int(value: object, default: int, name: str) -> int:
    """Return an integer value parsed from *value* with validation.

    Args:
        value: Raw value provided by the caller.
        default: Default integer used when *value* is ``None``.
        name: Name of the argument for error messages.

    Returns:
        int: Parsed integer value.

    Raises:
        TypeError: If *value* cannot be interpreted as an integer.
        ValueError: If string conversions fail integer parsing.
    """

    if value is None:
        return default
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer, not boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value.strip())
    raise TypeError(f"{name} must be an integer-compatible value")


def _coerce_str(value: object, default: str, name: str) -> str:
    """Return a string derived from *value* with validation.

    Args:
        value: Raw value provided by the caller.
        default: Default string used when *value* is ``None``.
        name: Name of the argument for error messages.

    Returns:
        str: Validated string value.

    Raises:
        TypeError: If *value* is not string-like.
    """

    if value is None:
        return default
    if isinstance(value, str):
        return value
    raise TypeError(f"{name} must be a string value")


def _coerce_bool(value: object, default: bool) -> bool:
    """Return a boolean flag derived from *value* with validation.

    Args:
        value: Raw value provided by the caller.
        default: Default boolean used when *value* is ``None``.

    Returns:
        bool: Parsed boolean value.
    """

    interpreted = interpret_optional_bool(value)
    if interpreted is None:
        return default
    return interpreted


def _coerce_section_builder(
    value: object,
    default: Callable[[Sequence[AdviceEntry]], Sequence[str]] | None,
    name: str,
) -> Callable[[Sequence[AdviceEntry]], Sequence[str]] | None:
    """Validate an optional advice section builder callback.

    Args:
        value: Raw value provided by the caller.
        default: Default callback used when *value* is ``None``.
        name: Name of the argument for error messages.

    Returns:
        Callable[[Sequence[AdviceEntry]], Sequence[str]] | None: Validated
        callback or ``None``.

    Raises:
        TypeError: If *value* is not callable.
    """

    if value is None:
        return default
    if callable(value):
        return cast(Callable[[Sequence[AdviceEntry]], Sequence[str]], value)
    raise TypeError(f"{name} must be callable or None")


def write_json_report(result: RunResult, path: Path) -> None:
    """Write a JSON report summarising tool outcomes.

    Args:
        result: Completed orchestrator run result to serialise.
        path: Destination path that receives the JSON payload.
    """
    total_actions = len(result.outcomes)
    failed_actions = sum(1 for outcome in result.outcomes if not outcome.ok)
    cached_actions = sum(1 for outcome in result.outcomes if outcome.cached)

    payload = {
        "root": str(result.root),
        "files": [str(p) for p in result.files],
        "outcomes": [serialize_outcome(outcome) for outcome in result.outcomes],
        "analysis": result.analysis,
        "actions": {
            "total": total_actions,
            "failed": failed_actions,
            "cached": cached_actions,
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_sarif_report(result: RunResult, path: Path) -> None:
    """Emit a SARIF document compatible with GitHub and other tools.

    Args:
        result: Completed orchestrator run result to serialise.
        path: Destination path that receives the SARIF document.
    """
    runs: list[dict[str, object]] = []
    for tool_name, diagnostics in _group_diagnostics_by_tool(result):
        version = result.tool_versions.get(tool_name)
        run = _build_sarif_run(tool_name, diagnostics, version)
        runs.append(run)

    sarif_doc = {
        "version": SARIF_VERSION,
        "$schema": SARIF_SCHEMA,
        "runs": runs,
    }
    path.write_text(json.dumps(sarif_doc, indent=2), encoding="utf-8")


def _build_sarif_run(
    tool_name: str,
    diagnostics: Sequence[Diagnostic],
    version: str | None,
) -> dict[str, object]:
    """Construct the SARIF run payload for a single tool.

    Args:
        tool_name: Name of the tool that emitted *diagnostics*.
        diagnostics: Collection of diagnostics associated with *tool_name*.
        version: Optional tool version string recorded with the run.

    Returns:
        dict[str, object]: SARIF-compliant run dictionary.
    """
    rules: dict[str, dict[str, object]] = {}
    results: list[dict[str, object]] = []

    for diag in diagnostics:
        rule_id = diag.code or tool_name
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": diag.message[:120]},
            }

        result_entry: dict[str, object] = {
            "ruleId": rule_id,
            "level": severity_to_sarif(diag.severity),
            "message": {"text": diag.message},
        }
        if diag.file:
            physical_location: dict[str, object] = {
                "artifactLocation": {"uri": diag.file},
            }
            region: dict[str, int] = {}
            if diag.line is not None:
                region["startLine"] = int(diag.line)
            if diag.column is not None:
                region["startColumn"] = int(diag.column)
            if region:
                physical_location["region"] = region
            result_entry["locations"] = [{"physicalLocation": physical_location}]
        results.append(result_entry)

    return {
        "tool": {
            "driver": {
                "name": tool_name,
                "version": version or "unknown",
                "rules": list(rules.values()) or None,
            },
        },
        "results": results,
    }


def write_pr_summary(
    result: RunResult,
    path: Path,
    *,
    options: PRSummaryOptions | None = None,
    **legacy_kwargs: object,
) -> None:
    """Render a Markdown summary for pull requests.

    Args:
        result: Completed orchestrator run result to summarise.
        path: Destination path that receives the Markdown summary.
        options: Optional structured configuration for the summary renderer.
        **legacy_kwargs: Backwards-compatible keyword arguments from older callers.

    Raises:
        TypeError: If conflicting or unexpected keyword arguments are supplied.
    """

    settings = _options_from_legacy_kwargs(options, legacy_kwargs)
    config = _build_summary_config(settings)
    diagnostics = _collect_diagnostics(result)
    filtered_pairs = _filter_diagnostics(diagnostics, config.min_rank)
    summary_entries = _build_summary_entries(filtered_pairs, config)
    advice_context = _build_advice_context(filtered_pairs, config)

    lines = ["# Lint Summary", ""]
    summary_lines, truncated_count = _format_summary_entries(
        summary_entries,
        config,
        advice_context,
    )
    lines.extend(summary_lines)
    if truncated_count:
        lines.extend(["", f"…and {truncated_count} more diagnostics."])

    if config.advice.include:
        additional_lines = list(_build_advice_section_lines(advice_context, config))
        if additional_lines:
            if lines[-1] != "":
                lines.append("")
            lines.extend(additional_lines)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _options_from_legacy_kwargs(
    options: PRSummaryOptions | None,
    legacy_kwargs: dict[str, object],
) -> PRSummaryOptions:
    """Normalise legacy keyword arguments into a summary options object.

    Args:
        options: Explicit options object, if provided by the caller.
        legacy_kwargs: Raw keyword arguments from legacy call sites.

    Returns:
        PRSummaryOptions: Effective configuration for summary rendering.

    Raises:
        TypeError: If unexpected arguments remain after normalisation.
    """
    if options is not None and legacy_kwargs:
        raise TypeError("write_pr_summary() received both options and legacy keyword arguments")
    if options is not None:
        return options

    settings = PRSummaryOptions()
    values = {
        "limit": settings.limit,
        "min_severity": settings.min_severity,
        "template": settings.template,
        "include_advice": settings.include_advice,
        "advice_limit": settings.advice_limit,
        "advice_template": settings.advice_template,
        "advice_section_builder": settings.advice_section_builder,
    }
    extracted: dict[str, object] = {}
    for key in list(legacy_kwargs):
        if key not in values:
            raise TypeError(f"Unexpected keyword argument: {key}")
        extracted[key] = legacy_kwargs.pop(key)
    if legacy_kwargs:
        raise TypeError(f"Unexpected keyword arguments: {', '.join(sorted(legacy_kwargs))}")

    limit = _coerce_int(
        extracted.get("limit"),
        settings.limit,
        "limit",
    )
    advice_limit = _coerce_int(
        extracted.get("advice_limit"),
        settings.advice_limit,
        "advice_limit",
    )
    min_severity = _coerce_str(
        extracted.get("min_severity"),
        settings.min_severity,
        "min_severity",
    )
    template = _coerce_str(
        extracted.get("template"),
        settings.template,
        "template",
    )
    advice_template = _coerce_str(
        extracted.get("advice_template"),
        settings.advice_template,
        "advice_template",
    )
    include_advice = _coerce_bool(
        extracted.get("include_advice"),
        settings.include_advice,
    )
    section_builder = _coerce_section_builder(
        extracted.get("advice_section_builder"),
        settings.advice_section_builder,
        "advice_section_builder",
    )

    return PRSummaryOptions(
        limit=limit,
        min_severity=min_severity,
        template=template,
        include_advice=include_advice,
        advice_limit=advice_limit,
        advice_template=advice_template,
        advice_section_builder=section_builder,
    )


def _build_summary_config(settings: PRSummaryOptions) -> _SummaryConfig:
    """Convert public summary settings into an internal configuration.

    Args:
        settings: User-facing summary options.

    Returns:
        _SummaryConfig: Internal configuration describing rendering needs.
    """
    min_rank = _severity_rank(settings.min_severity, SEVERITY_ORDER)
    needs_advice_metadata = (
        settings.include_advice
        or ADVICE_PLACEHOLDER in settings.template
        or ADVICE_PLACEHOLDER in settings.advice_template
    )
    needs_highlight = HIGHLIGHT_PLACEHOLDER in settings.template
    advice_options = _AdviceOptions(
        include=settings.include_advice,
        limit=max(settings.advice_limit, 0),
        template=settings.advice_template,
        section_builder=settings.advice_section_builder,
        needs_metadata=needs_advice_metadata,
    )
    return _SummaryConfig(
        limit=max(settings.limit, 0),
        min_rank=min_rank,
        template=settings.template,
        needs_highlight=needs_highlight,
        advice=advice_options,
    )


def _collect_diagnostics(result: RunResult) -> list[tuple[Diagnostic, str]]:
    """Collect diagnostics paired with their originating tool names.

    Args:
        result: Completed orchestrator run result containing diagnostics.

    Returns:
        list[tuple[Diagnostic, str]]: Diagnostics with associated tool names.
    """

    collected: list[tuple[Diagnostic, str]] = []
    for outcome in result.outcomes:
        for diag in outcome.diagnostics:
            collected.append((diag, outcome.tool))
    return collected


def _filter_diagnostics(
    diagnostics: Sequence[tuple[Diagnostic, str]],
    min_rank: int,
) -> list[tuple[Diagnostic, str]]:
    """Filter diagnostics by severity rank and return them in sorted order.

    Args:
        diagnostics: Candidate diagnostics paired with tool names.
        min_rank: Inclusive severity rank threshold for rendering.

    Returns:
        list[tuple[Diagnostic, str]]: Diagnostics meeting the severity cut-off.
    """

    filtered = [pair for pair in diagnostics if SEVERITY_ORDER.get(pair[0].severity, UNKNOWN_SEVERITY_RANK) <= min_rank]
    filtered.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item[0].severity, UNKNOWN_SEVERITY_RANK),
            item[0].file or "",
            item[0].line or 0,
        ),
    )
    return filtered


def _build_summary_entries(
    diagnostics: Sequence[tuple[Diagnostic, str]],
    config: _SummaryConfig,
) -> list[_SummaryEntry]:
    """Convert filtered diagnostics into structured summary entries.

    Args:
        diagnostics: Diagnostics paired with originating tool names.
        config: Summary configuration controlling rendering behaviour.

    Returns:
        list[_SummaryEntry]: Enriched diagnostics ready for templating.
    """

    entries: list[_SummaryEntry] = []
    for diagnostic, tool in diagnostics:
        location = _format_location(diagnostic)
        highlighted = _highlight_markdown(diagnostic.message) if config.needs_highlight else diagnostic.message
        entries.append(
            _SummaryEntry(
                diagnostic=diagnostic,
                tool=tool,
                location=location,
                message=diagnostic.message,
                highlighted_message=highlighted,
            ),
        )
    return entries


def _build_advice_context(
    diagnostics: Sequence[tuple[Diagnostic, str]],
    config: _SummaryConfig,
) -> _AdviceContext:
    """Build advice metadata required by summary templates.

    Args:
        diagnostics: Diagnostics paired with tool names.
        config: Summary configuration describing advice requirements.

    Returns:
        _AdviceContext: Advice entries and derived metadata for templating.
    """

    options = config.advice
    if not options.needs_metadata:
        return _AdviceContext(entries=[], summary="", primary_body="", primary_category="", count=0)

    advice_inputs = _diagnostics_to_advice_inputs(diagnostics)
    advice_entries = _ADVICE_PROVIDER_CONTEXT.builder.build(advice_inputs)
    advice_count = len(advice_entries)
    if not advice_entries:
        return _AdviceContext(entries=[], summary="", primary_body="", primary_category="", count=0)

    limited = advice_entries[: options.limit]
    summary = "; ".join(f"{entry.category}: {entry.body}" for entry in limited)
    primary_category = str(advice_entries[0].category)
    primary_body = advice_entries[0].body
    return _AdviceContext(
        entries=advice_entries,
        summary=summary,
        primary_body=primary_body,
        primary_category=primary_category,
        count=advice_count,
    )


def _format_summary_entries(
    entries: Sequence[_SummaryEntry],
    config: _SummaryConfig,
    advice_context: _AdviceContext,
) -> tuple[list[str], int]:
    """Format summary lines and report truncated diagnostics.

    Args:
        entries: Prepared summary entries.
        config: Rendering configuration controlling template expansion.
        advice_context: Advice metadata available to the formatter.

    Returns:
        tuple[list[str], int]: Rendered lines and a count of truncated diagnostics.
    """

    lines: list[str] = []
    for index, entry in enumerate(entries):
        if index >= config.limit:
            break
        diag = entry.diagnostic
        formatted = config.template.format(
            severity=diag.severity.value.upper(),
            tool=entry.tool,
            message=entry.message,
            highlighted_message=entry.highlighted_message,
            location=entry.location,
            code=diag.code or "",
            advice_summary=advice_context.summary,
            advice_primary=advice_context.primary_body,
            advice_primary_category=advice_context.primary_category,
            advice_count=advice_context.count,
        )
        lines.append(formatted)

    truncated = max(len(entries) - config.limit, 0) if config.limit else len(entries)
    return lines, truncated


def _build_advice_section_lines(
    advice_context: _AdviceContext,
    config: _SummaryConfig,
) -> Sequence[str]:
    """Return advice section lines for the PR summary.

    Args:
        advice_context: Advice data derived from diagnostics.
        config: Rendering configuration with advice preferences.

    Returns:
        Sequence[str]: Advice section lines, or an empty sequence when no advice
        is available.
    """

    if not advice_context.entries:
        return []
    options = config.advice
    if options.section_builder is not None:
        return options.section_builder(advice_context.entries)
    return _build_advice_section(advice_context.entries, options.limit, options.template)


def _format_location(diagnostic: Diagnostic) -> str:
    """Return a human-readable location string for a diagnostic.

    Args:
        diagnostic: Diagnostic whose location should be rendered.

    Returns:
        str: File, line, and column information formatted for humans.
    """

    location = diagnostic.file or "<workspace>"
    if diagnostic.line is not None:
        location += f":{int(diagnostic.line)}"
        if diagnostic.column is not None:
            location += f":{int(diagnostic.column)}"
    return location


def _group_diagnostics_by_tool(
    result: RunResult,
) -> Iterable[tuple[str, list[Diagnostic]]]:
    """Group diagnostics by tool name.

    Args:
        result: Completed orchestrator run result containing diagnostics.

    Returns:
        Iterable[tuple[str, list[Diagnostic]]]: Tool names paired with diagnostics.
    """
    buckets: dict[str, list[Diagnostic]] = {}
    for outcome in result.outcomes:
        if not outcome.diagnostics:
            continue
        buckets.setdefault(outcome.tool, []).extend(outcome.diagnostics)
    return sorted(buckets.items(), key=lambda item: item[0])


def _severity_rank(value: str | Severity, mapping: dict[Severity, int]) -> int:
    """Return the severity rank associated with *value*.

    Args:
        value: Severity instance or textual severity label.
        mapping: Lookup table mapping severities to rank integers.

    Returns:
        int: Rank value corresponding to *value*.
    """
    if isinstance(value, Severity):
        return mapping.get(value, mapping[Severity.WARNING])
    normalized = str(value).strip().lower()
    for sev, rank in mapping.items():
        if sev.value == normalized:
            return rank
    return mapping[Severity.WARNING]


def _build_advice_section(
    advice_entries: Sequence[AdviceEntry],
    limit: int,
    template: str,
) -> list[str]:
    """Render the optional advice section for a summary.

    Args:
        advice_entries: Advice entries generated for the run.
        limit: Maximum number of entries to render.
        template: Format string applied to each advice entry.

    Returns:
        list[str]: Advice section lines including headings and truncation notice.
    """
    if not advice_entries:
        return []

    section: list[str] = ["", "## SOLID Advice", ""]
    for entry in advice_entries[:limit]:
        rendered = template.format(category=entry.category, body=entry.body)
        section.append(rendered)
    if len(advice_entries) > limit:
        section.append(f"- …and {len(advice_entries) - limit} more advice items.")
    return section


def _diagnostics_to_advice_inputs(
    diagnostics: Sequence[tuple[Diagnostic, str]],
) -> list[tuple[str, int, str, str, str, str]]:
    """Convert diagnostics into tuples understood by the advice builder.

    Args:
        diagnostics: Diagnostics paired with originating tool names.

    Returns:
        list[tuple[str, int, str, str, str, str]]: Advice builder input tuples.
    """
    entries: list[tuple[str, int, str, str, str, str]] = []
    for diag, tool in diagnostics:
        file_path = diag.file or ""
        line_no = diag.line if diag.line is not None else -1
        function = diag.function or ""
        tool_name = (diag.tool or tool or "").strip()
        code = (diag.code or "-").strip() or "-"
        message = diag.message.splitlines()[0]
        entries.append((file_path, line_no, function, tool_name, code, message))
    return entries


def _highlight_markdown(message: str) -> str:
    """Highlight code spans in Markdown messages using annotation metadata.

    Args:
        message: Raw diagnostic message to annotate.

    Returns:
        str: Message with highlighted spans wrapped in Markdown emphasis.
    """
    spans = _ADVICE_PROVIDER_CONTEXT.annotation_engine.message_spans(message)
    if not spans:
        return message
    sorted_spans = sorted(spans, key=lambda span: (span.start, span.end))
    result: list[str] = []
    cursor = 0
    for span in sorted_spans:
        start, end = span.start, span.end
        if start < cursor:
            continue
        result.append(message[cursor:start])
        token = message[start:end]
        key = cast(HighlightKind, span.kind) if span.kind is not None else _DEFAULT_HIGHLIGHT_KIND
        wrapper = _HIGHLIGHT_WRAPPERS.get(key, _DEFAULT_HIGHLIGHT_WRAPPER)
        result.append(f"{wrapper.prefix}{token}{wrapper.suffix}")
        cursor = end
    result.append(message[cursor:])
    return "".join(result)


def set_annotation_provider(provider: AnnotationProvider) -> None:
    """Override the annotation provider used by report emitters.

    Args:
        provider: Provider that should service future annotation requests.
    """

    _ADVICE_PROVIDER_CONTEXT.replace(provider)
