"""Translate CLI options into runtime configuration objects."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List, Literal, cast

from ..config import Config, ExecutionConfig, FileDiscoveryConfig, OutputConfig
from ..config_loader import ConfigLoader
from ..logging import warn
from .options import LintOptions, ToolFilters

DEFAULT_TOOL_FILTERS: Dict[str, List[str]] = {
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

DEFAULT_EXCLUDES = [
    Path(".venv"),
    Path(".git"),
    Path("build"),
    Path("dist"),
    Path(".mypy_cache"),
    Path(".ruff_cache"),
    Path(".pytest_cache"),
    Path(".tox"),
    Path(".eggs"),
    Path(".tool-cache"),
    Path(".cache"),
]


def build_config(options: LintOptions) -> Config:
    """Translate CLI option data into an executable :class:`Config`."""

    project_root = options.root.resolve()
    loader = ConfigLoader.for_root(project_root)
    load_result = loader.load_with_trace(strict=options.strict_config)
    if load_result.warnings and not options.strict_config:
        for message in load_result.warnings:
            warn(message)
    base_config = load_result.config

    file_cfg = _build_file_discovery(base_config.file_discovery, options, project_root)
    output_cfg = _build_output(base_config.output, options, project_root)
    execution_cfg = _build_execution(base_config.execution, options, project_root)

    return Config(
        file_discovery=file_cfg,
        output=output_cfg,
        execution=execution_cfg,
        dedupe=replace(base_config.dedupe),
        severity_rules=list(base_config.severity_rules),
        tool_settings={
            tool: dict(settings)
            for tool, settings in base_config.tool_settings.items()
        },
    )


def _build_file_discovery(
    current: FileDiscoveryConfig, options: LintOptions, project_root: Path
) -> FileDiscoveryConfig:
    provided = options.provided

    roots = _unique_paths(_ensure_abs(project_root, path) for path in current.roots)
    if project_root not in roots:
        roots.insert(0, project_root)

    if "dirs" in provided:
        for directory in options.dirs:
            resolved = directory if directory.is_absolute() else (project_root / directory)
            roots.append(resolved.resolve())

    explicit_files: List[Path] = [path.resolve() for path in current.explicit_files]
    if "paths" in provided:
        for path in options.paths:
            resolved = path if path.is_absolute() else project_root / path
            if resolved.is_dir():
                roots.append(resolved.resolve())
            else:
                explicit_files.append(resolved.resolve())

    roots = _unique_paths(roots)
    explicit_files = _existing_unique_paths(explicit_files)

    excludes = _unique_paths([path.resolve() for path in current.excludes])
    for default_path in DEFAULT_EXCLUDES:
        resolved = _resolve_path(project_root, default_path).resolve()
        if resolved not in excludes:
            excludes.append(resolved)

    if "exclude" in provided:
        for path in options.exclude:
            resolved = _resolve_path(project_root, path).resolve()
            if resolved not in excludes:
                excludes.append(resolved)

    paths_from_stdin = (
        options.paths_from_stdin
        if "paths_from_stdin" in provided
        else current.paths_from_stdin
    )
    changed_only = (
        options.changed_only if "changed_only" in provided else current.changed_only
    )
    diff_ref = options.diff_ref if "diff_ref" in provided else current.diff_ref
    include_untracked = (
        options.include_untracked
        if "include_untracked" in provided
        else current.include_untracked
    )
    base_branch = (
        options.base_branch if "base_branch" in provided else current.base_branch
    )

    return replace(
        current,
        roots=roots,
        excludes=excludes,
        paths_from_stdin=paths_from_stdin,
        changed_only=changed_only,
        diff_ref=diff_ref,
        include_untracked=include_untracked,
        base_branch=base_branch,
        explicit_files=explicit_files,
    )


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

    verbose = options.verbose if "verbose" in provided else current.verbose
    quiet = options.quiet if "quiet" in provided else current.quiet
    color = (
        (not options.no_color) if "no_color" in provided else current.color
    )
    emoji = (
        (not options.no_emoji) if "no_emoji" in provided else current.emoji
    )
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

    return replace(
        current,
        verbose=verbose,
        quiet=quiet,
        color=color,
        emoji=emoji,
        show_passing=show_passing,
        output=output_mode,
        tool_filters=tool_filters,
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
        list(options.language)
        if "language" in provided
        else list(current.languages)
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

    return replace(
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
    )


def _unique_paths(paths: Iterable[Path]) -> List[Path]:
    seen: set[Path] = set()
    result: List[Path] = []
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


def _existing_unique_paths(paths: Iterable[Path]) -> List[Path]:
    collected: List[Path] = []
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


def _parse_filters(specs: List[str]) -> ToolFilters:
    filters: ToolFilters = {
        tool: patterns.copy() for tool, patterns in DEFAULT_TOOL_FILTERS.items()
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
