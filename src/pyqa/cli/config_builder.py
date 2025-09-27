# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Translate CLI options into runtime configuration objects."""

from __future__ import annotations

import re
import sys
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeVar, cast

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


def _build_default_tool_filters(*, include_test_suppressions: bool = True) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {
        tool: list(patterns) for tool, patterns in _BASE_TOOL_FILTERS.items()
    }
    if include_test_suppressions:
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


_PYTHON_VERSION_PATTERN = re.compile(r"(?P<major>\d{1,2})(?:[._-]?(?P<minor>\d{1,2}))?")


def build_config(options: LintOptions) -> Config:
    """Translate CLI option data into an executable :class:`Config`."""
    project_root = options.root.resolve()
    loader = ConfigLoader.for_root(project_root)
    load_result = loader.load_with_trace(strict=options.strict_config)
    base_config = load_result.config

    baseline = base_config.snapshot_shared_knobs()

    file_cfg = _build_file_discovery(base_config.file_discovery, options, project_root)
    output_cfg = _build_output(base_config.output, options, project_root)
    execution_cfg = _build_execution(base_config.execution, options, project_root)
    execution_cfg = _apply_python_version_detection(project_root, execution_cfg, options.provided)

    dedupe_cfg = base_config.dedupe.model_copy(deep=True)
    config = Config(
        file_discovery=file_cfg,
        output=output_cfg,
        execution=execution_cfg,
        dedupe=dedupe_cfg,
        severity_rules=list(base_config.severity_rules),
        tool_settings={
            tool: dict(settings) for tool, settings in base_config.tool_settings.items()
        },
    )
    if "sensitivity" in options.provided and options.sensitivity:
        config.severity.sensitivity = options.sensitivity

    config.apply_sensitivity_profile(cli_overrides=options.provided)
    if "max_complexity" in options.provided and options.max_complexity is not None:
        config.complexity.max_complexity = options.max_complexity
    if "max_arguments" in options.provided and options.max_arguments is not None:
        config.complexity.max_arguments = options.max_arguments
    if "type_checking" in options.provided and options.type_checking:
        level = options.type_checking.lower()
        if level not in {"lenient", "standard", "strict"}:
            raise ValueError("--type-checking must be one of: lenient, standard, strict")
        config.strictness.type_checking = cast("Literal['lenient', 'standard', 'strict']", level)
    if "bandit_severity" in options.provided and options.bandit_severity:
        config.severity.bandit_level = options.bandit_severity
    if "bandit_confidence" in options.provided and options.bandit_confidence:
        config.severity.bandit_confidence = options.bandit_confidence
    if "pylint_fail_under" in options.provided and options.pylint_fail_under is not None:
        config.severity.pylint_fail_under = options.pylint_fail_under

    config.apply_shared_defaults(override=True, baseline=baseline)
    return config


def _apply_python_version_detection(
    project_root: Path,
    current: ExecutionConfig,
    provided: set[str],
) -> ExecutionConfig:
    cli_specified = "python_version" in provided
    if cli_specified:
        normalized = _normalize_python_version(current.python_version)
        return _model_clone(current, python_version=normalized)

    forced = (
        _python_version_from_pyproject(project_root)
        or _python_version_from_python_version_file(project_root)
        or _normalize_python_version(current.python_version)
        or _default_interpreter_python_version()
    )
    return _model_clone(current, python_version=forced)


def _default_interpreter_python_version() -> str:
    info = sys.version_info
    return f"{info.major}.{info.minor}"


def _normalize_python_version(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    lowered = lowered.removeprefix("python")
    lowered = lowered.removeprefix("py")
    match = _PYTHON_VERSION_PATTERN.search(lowered)
    if not match:
        return None
    major = int(match.group("major"))
    minor_group = match.group("minor")
    minor = int(minor_group) if minor_group is not None and minor_group != "" else 0
    return f"{major}.{minor}"


def _python_version_from_python_version_file(root: Path) -> str | None:
    candidate = root / ".python-version"
    if not candidate.is_file():
        return None
    try:
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            normalized = _normalize_python_version(line)
            if normalized:
                return normalized
    except OSError:
        return None
    return None


def _python_version_from_pyproject(root: Path) -> str | None:
    candidate = root / "pyproject.toml"
    if not candidate.is_file():
        return None
    try:
        raw = candidate.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError:
        return None

    candidates: list[str] = []
    project_section = data.get("project")
    if isinstance(project_section, dict):
        requires = project_section.get("requires-python")
        if isinstance(requires, str):
            candidates.append(requires)

    tool_section = data.get("tool")
    if isinstance(tool_section, dict):
        poetry_section = tool_section.get("poetry")
        if isinstance(poetry_section, dict):
            dependencies = poetry_section.get("dependencies")
            if isinstance(dependencies, dict):
                poetry_python = dependencies.get("python")
                if isinstance(poetry_python, str):
                    candidates.append(poetry_python)

        hatch_section = tool_section.get("hatch")
        if isinstance(hatch_section, dict):
            envs = hatch_section.get("envs")
            if isinstance(envs, dict):
                default_env = envs.get("default")
                if isinstance(default_env, dict):
                    version = default_env.get("python")
                    if isinstance(version, str):
                        candidates.append(version)

    for candidate_value in candidates:
        normalized = _normalize_python_version(candidate_value)
        if normalized:
            return normalized
    return None


def _build_file_discovery(
    current: FileDiscoveryConfig,
    options: LintOptions,
    project_root: Path,
) -> FileDiscoveryConfig:
    provided = options.provided
    roots = _resolved_roots(current, project_root, options)
    explicit_files, boundaries = _resolved_explicit_files(current, options, project_root, roots)
    excludes = _resolved_excludes(current, options, project_root)

    paths_from_stdin = _select_flag(
        options.paths_from_stdin,
        current.paths_from_stdin,
        "paths_from_stdin",
        provided,
    )
    changed_only = _select_flag(
        options.changed_only,
        current.changed_only,
        "changed_only",
        provided,
    )
    diff_ref = _select_value(options.diff_ref, current.diff_ref, "diff_ref", provided)
    include_untracked = _select_flag(
        options.include_untracked,
        current.include_untracked,
        "include_untracked",
        provided,
    )
    base_branch = _select_value(options.base_branch, current.base_branch, "base_branch", provided)

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
            resolved_path = (path if path.is_absolute() else project_root / path).resolve()
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
    filtered_files = [path for path in explicit_files if _is_within_any(path, boundaries)]
    roots.clear()
    roots.extend(filtered_roots)
    return filtered_files, boundaries


def _filter_roots_within_boundaries(
    roots: Sequence[Path],
    boundaries: Sequence[Path],
) -> list[Path]:
    matching = [path for path in roots if _is_within_any(path, boundaries)]
    if matching:
        merged = list(matching)
        merged.extend(path for path in boundaries if path not in matching and path.is_dir())
        return _unique_paths(merged)
    boundary_dirs = [path for path in boundaries if path.is_dir()]
    return _unique_paths(boundary_dirs)


def _derive_boundaries(user_dirs: Sequence[Path], user_files: Sequence[Path]) -> Iterable[Path]:
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
    value: str | None,
    fallback: str | None,
    key: str,
    provided: set[str],
) -> str | None:
    return value if key in provided else fallback


def _build_output(current: OutputConfig, options: LintOptions, project_root: Path) -> OutputConfig:
    provided = options.provided

    filters = _merge_output_tool_filters(current.tool_filters, options)
    flags = _resolve_output_flags(current, options, provided)
    output_mode = _resolve_output_mode(current, options, provided)
    summary = _resolve_pr_summary_settings(current, options, provided, project_root)

    show_passing = flags.show_passing
    show_stats = flags.show_stats
    if flags.quiet:
        show_passing = False
        show_stats = False

    return _model_clone(
        current,
        verbose=flags.verbose,
        quiet=flags.quiet,
        color=flags.color,
        emoji=flags.emoji,
        show_passing=show_passing,
        show_stats=show_stats,
        advice=flags.advice,
        output=output_mode,
        tool_filters=filters,
        pr_summary_out=summary.out_path,
        pr_summary_limit=summary.limit,
        pr_summary_min_severity=summary.min_severity,
        pr_summary_template=summary.template,
    )


@dataclass(frozen=True)
class _OutputFlags:
    verbose: bool
    quiet: bool
    color: bool
    emoji: bool
    show_passing: bool
    show_stats: bool
    advice: bool


@dataclass(frozen=True)
class _OutputSummary:
    out_path: Path | None
    limit: int
    min_severity: str
    template: str


def _merge_output_tool_filters(
    current_filters: Mapping[str, list[str]],
    options: LintOptions,
) -> ToolFilters:
    include_test_filters = not options.disable_test_suppressions
    base_filters = (
        DEFAULT_TOOL_FILTERS
        if include_test_filters
        else _build_default_tool_filters(include_test_suppressions=False)
    )

    merged: ToolFilters = {tool: patterns.copy() for tool, patterns in base_filters.items()}
    for tool, patterns in current_filters.items():
        merged.setdefault(tool, []).extend(patterns)

    if "filters" in options.provided:
        for tool, patterns in _parse_filters(options.filters).items():
            merged.setdefault(tool, []).extend(patterns)

    return {tool: list(dict.fromkeys(patterns)) for tool, patterns in merged.items() if patterns}


def _resolve_output_flags(
    current: OutputConfig,
    options: LintOptions,
    provided: set[str],
) -> _OutputFlags:
    verbose = options.verbose if "verbose" in provided else current.verbose
    quiet = options.quiet if "quiet" in provided else current.quiet
    color = (not options.no_color) if "no_color" in provided else current.color
    emoji = (not options.no_emoji) if "no_emoji" in provided else current.emoji
    show_passing = options.show_passing if "show_passing" in provided else current.show_passing
    show_stats = (not options.no_stats) if "no_stats" in provided else current.show_stats
    advice = options.advice if "advice" in provided else current.advice
    return _OutputFlags(
        verbose=verbose,
        quiet=quiet,
        color=color,
        emoji=emoji,
        show_passing=show_passing,
        show_stats=show_stats,
        advice=advice,
    )


def _resolve_output_mode(
    current: OutputConfig,
    options: LintOptions,
    provided: set[str],
) -> str:
    if "output_mode" not in provided:
        return current.output
    return _normalize_output_mode(options.output_mode)


def _resolve_pr_summary_settings(
    current: OutputConfig,
    options: LintOptions,
    provided: set[str],
    project_root: Path,
) -> _OutputSummary:
    out_path = (
        _resolve_optional_path(project_root, options.pr_summary_out)
        if "pr_summary_out" in provided
        else current.pr_summary_out
    )
    limit = options.pr_summary_limit if "pr_summary_limit" in provided else current.pr_summary_limit
    min_severity = (
        _normalize_min_severity(options.pr_summary_min_severity)
        if "pr_summary_min_severity" in provided
        else current.pr_summary_min_severity
    )
    template = (
        options.pr_summary_template
        if "pr_summary_template" in provided
        else current.pr_summary_template
    )
    return _OutputSummary(
        out_path=out_path,
        limit=limit,
        min_severity=min_severity,
        template=template,
    )


def _build_execution(
    current: ExecutionConfig,
    options: LintOptions,
    project_root: Path,
) -> ExecutionConfig:
    provided = options.provided

    only = list(options.only) if "only" in provided else list(current.only)
    language = list(options.language) if "language" in provided else list(current.languages)
    fix_only = options.fix_only if "fix_only" in provided else current.fix_only
    check_only = options.check_only if "check_only" in provided else current.check_only
    bail = options.bail if "bail" in provided else current.bail

    if "jobs" in provided:
        jobs = options.jobs
    else:
        jobs = current.jobs
    if bail:
        jobs = 1

    cache_enabled = (not options.no_cache) if "no_cache" in provided else current.cache_enabled
    cache_dir = (
        _resolve_path(project_root, options.cache_dir).resolve()
        if "cache_dir" in provided
        else current.cache_dir
    )
    use_local_linters = (
        options.use_local_linters if "use_local_linters" in provided else current.use_local_linters
    )
    line_length = options.line_length if "line_length" in provided else current.line_length
    sql_dialect = options.sql_dialect if "sql_dialect" in provided else current.sql_dialect
    python_version = (
        options.python_version if "python_version" in provided else current.python_version
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
        python_version=python_version,
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
    filters: ToolFilters = {tool: list(patterns) for tool, patterns in DEFAULT_TOOL_FILTERS.items()}
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
    return cast("OutputMode", normalized)


def _normalize_min_severity(value: str) -> SummarySeverity:
    normalized = value.lower()
    if normalized not in _ALLOWED_SUMMARY_SEVERITIES:
        raise ValueError(f"invalid summary severity '{value}'")
    return cast("SummarySeverity", normalized)


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
    return cast("ModelT", instance.model_copy(update=updates, deep=True))
