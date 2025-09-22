"""Translate CLI options into runtime configuration objects."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, cast

from ..config import (
    Config,
    DedupeConfig,
    ExecutionConfig,
    FileDiscoveryConfig,
    OutputConfig,
)
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

    root = options.root

    roots: List[Path] = [root]
    for directory in options.dirs:
        resolved = directory if directory.is_absolute() else root / directory
        roots.append(resolved)

    explicit_files: List[Path] = []
    for path in options.paths:
        resolved = path if path.is_absolute() else root / path
        if resolved.is_dir():
            roots.append(resolved)
        else:
            explicit_files.append(resolved)

    unique_roots = _unique_paths(roots)

    exclude_paths = DEFAULT_EXCLUDES + options.exclude
    file_cfg = FileDiscoveryConfig(
        roots=unique_roots,
        excludes=[_resolve_path(root, p) for p in exclude_paths],
        paths_from_stdin=options.paths_from_stdin,
        changed_only=options.changed_only,
        diff_ref=options.diff_ref,
        include_untracked=options.include_untracked,
        base_branch=options.base_branch,
        explicit_files=[p for p in explicit_files if p.exists()],
    )

    tool_filters = _parse_filters(options.filters)
    show_passing = options.show_passing and not options.quiet

    output_cfg = OutputConfig(
        verbose=options.verbose,
        emoji=not options.no_emoji,
        color=not options.no_color,
        show_passing=show_passing,
        output=_normalize_output_mode(options.output_mode),
        pr_summary_out=options.pr_summary_out,
        pr_summary_limit=options.pr_summary_limit,
        pr_summary_min_severity=_normalize_min_severity(
            options.pr_summary_min_severity
        ),
        pr_summary_template=options.pr_summary_template,
        quiet=options.quiet,
        tool_filters=tool_filters,
    )

    cache_dir = (
        options.cache_dir
        if options.cache_dir.is_absolute()
        else root / options.cache_dir
    )

    exec_cfg = ExecutionConfig(
        only=list(options.only),
        languages=list(options.language),
        fix_only=options.fix_only,
        check_only=options.check_only,
        jobs=options.jobs if not options.bail else 1,
        cache_enabled=not options.no_cache,
        cache_dir=cache_dir,
        bail=options.bail,
        use_local_linters=options.use_local_linters,
    )

    return Config(
        file_discovery=file_cfg,
        output=output_cfg,
        execution=exec_cfg,
        dedupe=DedupeConfig(),
    )


def _unique_paths(paths: List[Path]) -> List[Path]:
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
