# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Translate CLI options into runtime configuration objects."""

from __future__ import annotations

from pathlib import Path
from typing import Final, Iterable, Literal, Sequence, TypeVar, cast

from pydantic import BaseModel

from ..config import Config, ExecutionConfig, FileDiscoveryConfig, OutputConfig
from ..config_loader import ConfigLoader
from ..testing.suppressions import flatten_test_suppressions
from .options import LintOptions, ToolFilters

ModelT = TypeVar("ModelT", bound=BaseModel)


_BASE_TOOL_FILTERS: Final[dict[str, list[str]]] = {
    "bandit": [
        r"^Run started:.*$",
        r"^Test results:$",
        r"^No issues identified\.$",
        r"^Files skipped \(.*\):$",
    ],
    "black": [
        r"^All done! [0-9]+ files? (re)?formatted\.$",
        r"^All done! ✨ .* files? left unchanged\.$",
    ],
    "isort": [
        r"^SUCCESS: .* files? are correctly sorted and formatted\.$",
        r"^Nothing to do\.$",
    ],
    "mypy": [r"^Success:.*"],
    "pylint": [
        r"^Your code has been rated at 10\.00/10.*$",
        r"^----",
        r"^Your code has been rated",
        r"^$",
        r"^\*\*\*",
    ],
    "pyright": [
        r"^No configuration file found\..*",
        r"^No pyright configuration found\..*",
        r"^0 errors, 0 warnings, 0 informations$",
        r"^Found 0 errors in .* files? \(.*\)$",
    ],
    "pytest": [
        r"^=+ .* in .*s =+$",
        r"^collected \[0-9]+ items$",
        r"^platform .* - Python .*",
        r"^cache cleared$",
    ],
    "ruff": [
        r"^Found 0 errors\..*$",
        r"^All checks passed!$",
        r"^.* 0 files? reformatted.*$",
    ],
    "vulture": [r"^No dead code found$"],
}


def _build_default_tool_filters() -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {
        tool: list(patterns) for tool, patterns in _BASE_TOOL_FILTERS.items()
    }
    for tool, patterns in flatten_test_suppressions().items():
        merged.setdefault(tool, []).extend(patterns)
    return {tool: list(dict.fromkeys(patterns)) for tool, patterns in merged.items()}


DEFAULT_TOOL_FILTERS: Final[dict[str, list[str]]] = _build_default_tool_filters()

DEFAULT_EXCLUDES: Final[tuple[Path, ...]] = (
    Path(".venv"),
    Path(".git"),
    Path("build"),
    Path("dist"),
    Path(".mypy_cache"),
    Path(".ruff_cache"),
    Path(".pytest_cache"),
    Path(".tox"),
    Path(".eggs"),
    Path(".lint-cache"),
    Path(".cache"),
    Path(".aider.chat.history.md"),
    Path("src/.lint-cache"),
)


def build_config(options: LintOptions) -> Config:
    """Translate CLI option data into an executable :class:`Config`."""

    project_root = options.root.resolve()
    loader = ConfigLoader.for_root(project_root)
    load_result = loader.load_with_trace(strict=options.strict_config)
    base_config = load_result.config

    file_cfg = _build_file_discovery(base_config.file_discovery, options, project_root)
    output_cfg = _build_output(base_config.output, options, project_root)
    execution_cfg = _build_execution(base_config.execution, options, project_root)

    dedupe_cfg = base_config.dedupe.model_copy(deep=True)
    return Config(
        file_discovery=file_cfg,
        output=output_cfg,
        execution=execution_cfg,
        dedupe=dedupe_cfg,
        severity_rules=list(base_config.severity_rules),
        tool_settings={
            tool: dict(settings) for tool, settings in base_config.tool_settings.items()
        },
    )


def _build_file_discovery(
    current: FileDiscoveryConfig, options: LintOptions, project_root: Path
) -> FileDiscoveryConfig:
    provided = options.provided
    roots = _resolved_roots(current, project_root, options)
    explicit_files, boundaries = _resolved_explicit_files(
        current, options, project_root, roots
    )
    excludes = _resolved_excludes(current, options, project_root)

    paths_from_stdin = _select_flag(
        options.paths_from_stdin, current.paths_from_stdin, "paths_from_stdin", provided
    )
    changed_only = _select_flag(
        options.changed_only, current.changed_only, "changed_only", provided
    )
    diff_ref = _select_value(options.diff_ref, current.diff_ref, "diff_ref", provided)
    include_untracked = _select_flag(
        options.include_untracked,
        current.include_untracked,
        "include_untracked",
        provided,
    )
    base_branch = _select_value(
        options.base_branch, current.base_branch, "base_branch", provided
    )

    return _model_clone(
        current,
        roots=roots,
        excludes=excludes,
        paths_from_stdin=paths_from_stdin,
        changed_only=changed_only,
        diff_ref=diff_ref,
        include_untracked=include_untracked,
        base_branch=base_branch,
        explicit_files=explicit_files,
        limit_to=boundaries,
    )


def _resolved_roots(
    current: FileDiscoveryConfig,
    project_root: Path,
    options: LintOptions,
) -> list[Path]:
    roots = _unique_paths(_ensure_abs(project_root, path) for path in current.roots)
    if project_root not in roots:
        roots.insert(0, project_root)

    if "dirs" in options.provided:
        resolved_dirs = (
            directory if directory.is_absolute() else (project_root / directory)
            for directory in options.dirs
        )
        roots.extend(path.resolve() for path in resolved_dirs)

    return _unique_paths(roots)


def _resolved_explicit_files(
    current: FileDiscoveryConfig,
    options: LintOptions,
    project_root: Path,
    roots: list[Path],
) -> tuple[list[Path], list[Path]]:
    explicit_files: list[Path] = _existing_unique_paths(current.explicit_files)
    user_dirs: list[Path] = []
    user_files: list[Path] = []

    if "paths" in options.provided:
        for path in options.paths:
            resolved_path = (
                path if path.is_absolute() else project_root / path
            ).resolve()
            if resolved_path.is_dir():
                roots.append(resolved_path)
                user_dirs.append(resolved_path)
            else:
                user_files.append(resolved_path)
                if resolved_path not in explicit_files:
                    explicit_files.append(resolved_path)

    boundaries = _unique_paths(
        boundary for boundary in _derive_boundaries(user_dirs, user_files) if boundary
    )
    if not boundaries:
        return explicit_files, []

    filtered_roots = _filter_roots_within_boundaries(roots, boundaries)
    filtered_files = [
        path for path in explicit_files if _is_within_any(path, boundaries)
    ]
    roots.clear()
    roots.extend(filtered_roots)
    return filtered_files, boundaries


def _filter_roots_within_boundaries(
    roots: Sequence[Path], boundaries: Sequence[Path]
) -> list[Path]:
    matching = [path for path in roots if _is_within_any(path, boundaries)]
    if matching:
        merged = list(matching)
        merged.extend(
            path for path in boundaries if path not in matching and path.is_dir()
        )
        return _unique_paths(merged)
    boundary_dirs = [path for path in boundaries if path.is_dir()]
    return _unique_paths(boundary_dirs)


def _derive_boundaries(
    user_dirs: Sequence[Path], user_files: Sequence[Path]
) -> Iterable[Path]:
    parents = [file_path.parent for file_path in user_files]
    for candidate in (*user_dirs, *parents):
        if candidate:
            yield candidate


def _resolved_excludes(
    current: FileDiscoveryConfig,
    options: LintOptions,
    project_root: Path,
) -> list[Path]:
    excludes = _unique_paths(path.resolve() for path in current.excludes)
    for default_path in DEFAULT_EXCLUDES:
        resolved = _resolve_path(project_root, default_path).resolve()
        if resolved not in excludes:
            excludes.append(resolved)
    if "exclude" in options.provided:
        for path in options.exclude:
            resolved = _resolve_path(project_root, path).resolve()
            if resolved not in excludes:
                excludes.append(resolved)
    return excludes


def _select_flag(candidate: bool, fallback: bool, key: str, provided: set[str]) -> bool:
    return candidate if key in provided else fallback


def _select_value(
    value: str | None, fallback: str | None, key: str, provided: set[str]
) -> str | None:
    return value if key in provided else fallback


def _build_output(
    current: OutputConfig, options: LintOptions, project_root: Path
) -> OutputConfig:
    provided = options.provided

    tool_filters: ToolFilters = {
        tool: patterns.copy() for tool, patterns in DEFAULT_TOOL_FILTERS.items()
    }
    for tool, patterns in current.tool_filters.items():
        tool_filters.setdefault(tool, []).extend(patterns)
    if "filters" in provided:
        parsed = _parse_filters(options.filters)
        for tool, patterns in parsed.items():
            tool_filters.setdefault(tool, []).extend(patterns)
    normalised_filters: ToolFilters = {
        tool: list(dict.fromkeys(patterns)) for tool, patterns in tool_filters.items()
    }

    verbose = options.verbose if "verbose" in provided else current.verbose
    quiet = options.quiet if "quiet" in provided else current.quiet
    color = (not options.no_color) if "no_color" in provided else current.color
    emoji = (not options.no_emoji) if "no_emoji" in provided else current.emoji
    output_mode = (
        _normalize_output_mode(options.output_mode)
        if "output_mode" in provided
        else current.output
    )
    show_passing = (
        options.show_passing if "show_passing" in provided else current.show_passing
    )
    if quiet:
        show_passing = False

    pr_summary_out = (
        _resolve_optional_path(project_root, options.pr_summary_out)
        if "pr_summary_out" in provided
        else current.pr_summary_out
    )
    pr_summary_limit = (
        options.pr_summary_limit
        if "pr_summary_limit" in provided
        else current.pr_summary_limit
    )
    pr_summary_min = (
        _normalize_min_severity(options.pr_summary_min_severity)
        if "pr_summary_min_severity" in provided
        else current.pr_summary_min_severity
    )
    pr_summary_template = (
        options.pr_summary_template
        if "pr_summary_template" in provided
        else current.pr_summary_template
    )

    return _model_clone(
        current,
        verbose=verbose,
        quiet=quiet,
        color=color,
        emoji=emoji,
        show_passing=show_passing,
        output=output_mode,
        tool_filters=normalised_filters,
        pr_summary_out=pr_summary_out,
        pr_summary_limit=pr_summary_limit,
        pr_summary_min_severity=pr_summary_min,
        pr_summary_template=pr_summary_template,
    )


def _build_execution(
    current: ExecutionConfig, options: LintOptions, project_root: Path
) -> ExecutionConfig:
    provided = options.provided

    only = list(options.only) if "only" in provided else list(current.only)
    language = (
        list(options.language) if "language" in provided else list(current.languages)
    )
    fix_only = options.fix_only if "fix_only" in provided else current.fix_only
    check_only = options.check_only if "check_only" in provided else current.check_only
    bail = options.bail if "bail" in provided else current.bail

    if "jobs" in provided:
        jobs = options.jobs
    else:
        jobs = current.jobs
    if bail:
        jobs = 1

    cache_enabled = (
        (not options.no_cache) if "no_cache" in provided else current.cache_enabled
    )
    cache_dir = (
        _resolve_path(project_root, options.cache_dir).resolve()
        if "cache_dir" in provided
        else current.cache_dir
    )
    use_local_linters = (
        options.use_local_linters
        if "use_local_linters" in provided
        else current.use_local_linters
    )
    line_length = (
        options.line_length if "line_length" in provided else current.line_length
    )
    sql_dialect = (
        options.sql_dialect if "sql_dialect" in provided else current.sql_dialect
    )

    return _model_clone(
        current,
        only=only,
        languages=language,
        fix_only=fix_only,
        check_only=check_only,
        jobs=jobs,
        cache_enabled=cache_enabled,
        cache_dir=cache_dir,
        bail=bail,
        use_local_linters=use_local_linters,
        line_length=line_length,
        sql_dialect=sql_dialect,
    )


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            result.append(resolved)
            seen.add(resolved)
    return result


def _resolve_path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else (root / path)


def _resolve_optional_path(root: Path, path: Path | None) -> Path | None:
    if path is None:
        return None
    return _resolve_path(root, path).resolve()


def _existing_unique_paths(paths: Iterable[Path]) -> list[Path]:
    collected: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if not resolved.exists():
            continue
        if resolved in seen:
            continue
        collected.append(resolved)
        seen.add(resolved)
    return collected


def _ensure_abs(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else (root / path).resolve()


def _is_within_any(path: Path, bounds: Iterable[Path]) -> bool:
    for bound in bounds:
        try:
            path.relative_to(bound)
            return True
        except ValueError:
            continue
    return False


def _parse_filters(specs: Iterable[str]) -> ToolFilters:
    filters: ToolFilters = {
        tool: list(patterns) for tool, patterns in DEFAULT_TOOL_FILTERS.items()
    }
    for spec in specs:
        if ":" not in spec:
            raise ValueError(f"Invalid filter '{spec}'. Expected TOOL:regex")
        tool, expressions = spec.split(":", 1)
        chunks = [chunk.strip() for chunk in expressions.split(";;") if chunk.strip()]
        if not chunks:
            continue
        filters.setdefault(tool.strip(), []).extend(chunks)
    return filters


def _normalize_output_mode(value: str) -> OutputMode:
    normalized = value.lower()
    if normalized not in _ALLOWED_OUTPUT_MODES:
        raise ValueError(f"invalid output mode '{value}'")
    return cast(OutputMode, normalized)


def _normalize_min_severity(value: str) -> SummarySeverity:
    normalized = value.lower()
    if normalized not in _ALLOWED_SUMMARY_SEVERITIES:
        raise ValueError(f"invalid summary severity '{value}'")
    return cast(SummarySeverity, normalized)


OutputMode = Literal["concise", "pretty", "raw"]
SummarySeverity = Literal["error", "warning", "notice", "note"]

_ALLOWED_OUTPUT_MODES: tuple[OutputMode, ...] = ("concise", "pretty", "raw")
_ALLOWED_SUMMARY_SEVERITIES: tuple[SummarySeverity, ...] = (
    "error",
    "warning",
    "notice",
    "note",
)


def _model_clone(instance: ModelT, **updates: object) -> ModelT:
    return cast(ModelT, instance.model_copy(update=updates, deep=True))
