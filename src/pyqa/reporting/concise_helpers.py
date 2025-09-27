"""Shared helpers for concise diagnostic collection and summaries."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..models import Diagnostic, RunResult, ToolOutcome

__all__ = [
    "ConciseEntry",
    "SummaryData",
    "collect_concise_entries",
    "compute_summary",
    "group_similar_entries",
    "resolve_root_path",
]


@dataclass(frozen=True)
class ConciseEntry:
    file_path: str
    line_no: int
    function: str
    tool_name: str
    code: str
    message: str


@dataclass(frozen=True)
class SummaryData:
    total_actions: int
    failed_actions: int
    diagnostics_count: int
    files_count: int


def resolve_root_path(root: Path | str) -> Path:
    root_path = Path(root)
    try:
        return root_path.resolve()
    except OSError:
        return root_path


def collect_concise_entries(result: RunResult) -> list[ConciseEntry]:
    root_path = resolve_root_path(result.root)
    return collect_entries_from_outcomes(result.outcomes, root_path)


def collect_entries_from_outcomes(
    outcomes: Sequence[ToolOutcome],
    root_path: Path,
    *,
    deduplicate: bool = True,
) -> list[ConciseEntry]:
    entries: list[ConciseEntry] = []
    seen: set[ConciseEntry] | None = set() if deduplicate else None
    for outcome in outcomes:
        for diag in outcome.diagnostics:
            entry = _build_concise_entry(diag, outcome, root_path)
            if seen is not None:
                if entry in seen:
                    continue
                seen.add(entry)
            entries.append(entry)
    return entries


def group_similar_entries(entries: Iterable[ConciseEntry]) -> list[ConciseEntry]:
    grouped: dict[
        tuple[str, int, str, str, str, str, str],
        dict[str, object],
    ] = {}
    ordered_keys: list[tuple[str, int, str, str, str, str, str]] = []

    for entry in entries:
        match = _MERGEABLE_MESSAGE.match(entry.message)
        file_path = entry.file_path
        line_no = entry.line_no
        function = entry.function
        tool_name = entry.tool_name
        code = entry.code
        message = entry.message

        if not match:
            sanitized_message = message.replace("`", "")
            grouped_key = (file_path, line_no, function, tool_name, code, sanitized_message, "")
            if grouped_key not in grouped:
                grouped[grouped_key] = {
                    "prefix": sanitized_message,
                    "suffix": "",
                    "details": [],
                    "message": sanitized_message,
                }
                ordered_keys.append(grouped_key)
            continue

        prefix = match.group("prefix").replace("`", "")
        detail = match.group("detail").replace("`", "")
        suffix = match.group("suffix").replace("`", "")
        if not detail:
            grouped_key = (file_path, line_no, function, tool_name, code, prefix + suffix, "")
            if grouped_key not in grouped:
                grouped[grouped_key] = {
                    "prefix": prefix,
                    "suffix": "",
                    "details": [],
                    "message": (prefix + suffix).strip(),
                }
                ordered_keys.append(grouped_key)
            continue

        grouped_key = (file_path, line_no, function, tool_name, code, prefix, suffix)
        bucket = grouped.get(grouped_key)
        if bucket is None:
            bucket = {
                "prefix": prefix,
                "suffix": suffix,
                "details": [],
                "message": (prefix + detail + suffix).strip(),
            }
            grouped[grouped_key] = bucket
            ordered_keys.append(grouped_key)
        details: list[str] = bucket["details"]  # type: ignore[assignment]
        if detail not in details:
            details.append(detail)

    merged: list[ConciseEntry] = []
    for grouped_key in ordered_keys:
        file_path, line_no, function, tool_name, code, prefix, suffix = grouped_key
        bucket = grouped[grouped_key]
        details: list[str] = bucket["details"]  # type: ignore[assignment]
        if not details or len(details) == 1:
            message = bucket["message"]  # type: ignore[assignment]
        else:
            joined = ", ".join(details)
            message = f"{prefix}{joined}{suffix}".strip()
        merged.append(
            ConciseEntry(
                file_path=file_path,
                line_no=line_no,
                function=function,
                tool_name=tool_name,
                code=code,
                message=message.replace("`", ""),
            ),
        )
    return merged


def compute_summary(result: RunResult, diagnostics_count: int) -> SummaryData:
    total_actions = len(result.outcomes)
    failed_actions = sum(1 for outcome in result.outcomes if not outcome.ok)
    files_count = len(result.files)
    return SummaryData(
        total_actions=total_actions,
        failed_actions=failed_actions,
        diagnostics_count=diagnostics_count,
        files_count=files_count,
    )


def _build_concise_entry(
    diag: Diagnostic,
    outcome: ToolOutcome,
    root_path: Path,
) -> ConciseEntry:
    tool_name = diag.tool or outcome.tool
    file_path = _normalize_concise_path(diag.file, root_path)
    line_no = diag.line if diag.line is not None else -1
    raw_code = diag.code or "-"
    code = raw_code.strip() or "-"
    raw_message = diag.message.splitlines()[0]
    message = _clean_message(code, raw_message) or "<no message provided>"
    function = _normalise_symbol(diag.function)
    return ConciseEntry(
        file_path=file_path,
        line_no=line_no,
        function=function,
        tool_name=tool_name,
        code=code,
        message=message,
    )


def _clean_message(code: str | None, message: str) -> str:
    if not message:
        return message

    first_line, newline, remainder = message.partition("\n")
    working = first_line.lstrip()
    normalized_code = (code or "").strip()

    if normalized_code and normalized_code != "-":
        patterns = [
            f"{normalized_code}: ",
            f"{normalized_code}:",
            f"{normalized_code} - ",
            f"{normalized_code} -",
            f"{normalized_code} ",
            f"[{normalized_code}] ",
            f"[{normalized_code}]",
        ]
        for pattern in patterns:
            if working.startswith(pattern):
                working = working[len(pattern) :]
                break
        else:
            working = working.removeprefix(normalized_code)

    cleaned_first = working.lstrip()
    if newline:
        return cleaned_first + "\n" + remainder
    return cleaned_first


def _normalise_symbol(value: str | None) -> str:
    if not value:
        return ""
    candidate = value.strip()
    if not candidate:
        return ""
    if "\n" in candidate:
        candidate = candidate.splitlines()[0].strip()
    if not candidate:
        return ""
    if candidate.startswith(("#", '"""', "'''")):
        return ""
    if any(char.isspace() for char in candidate):
        return ""
    allowed_symbols = {"_", ".", "-", ":", "<", ">", "[", "]", "(", ")"}
    if any(not ch.isalnum() and ch not in allowed_symbols for ch in candidate):
        return ""
    if len(candidate) > 80:
        candidate = f"{candidate[:77]}…"
    return candidate


def _normalize_concise_path(path_str: str | None, root: Path) -> str:
    if not path_str:
        return "<unknown>"
    candidate = Path(path_str)
    try:
        if candidate.is_absolute():
            try:
                candidate_resolved = candidate.resolve()
            except OSError:
                candidate_resolved = candidate
            try:
                root_resolved = root.resolve()
            except OSError:
                root_resolved = root
            try:
                return candidate_resolved.relative_to(root_resolved).as_posix()
            except ValueError:
                return candidate_resolved.as_posix()
        return candidate.as_posix()
    except OSError:
        return str(candidate)


_MERGEABLE_MESSAGE = re.compile(r"^(?P<prefix>.*?)(`(?P<detail>[^`]+)`)(?P<suffix>.*)$")
