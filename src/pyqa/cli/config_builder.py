# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Translate CLI options into runtime configuration objects."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Callable, Final, Literal, TypeVar, cast

from pydantic import BaseModel

from ..config import (
    BanditConfidence,
    BanditLevel,
    Config,
    ExecutionConfig,
    FileDiscoveryConfig,
    OutputConfig,
    SensitivityLevel,
    StrictnessLevel,
)
from ..config_utils import _existing_unique_paths as shared_existing_unique_paths
from ..config_utils import _unique_paths as shared_unique_paths
from ..config_loader import ConfigLoader
from ..filesystem.paths import normalize_path
from ..testing.suppressions import flatten_test_suppressions
from ..tools.catalog_metadata import catalog_general_suppressions
from .options import LintOptions, ToolFilters
from .python_version_resolver import resolve_python_version

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


class LintOptionKey(str, Enum):
    """Enumerate CLI option identifiers used for configuration overrides."""

    SENSITIVITY = "sensitivity"
    MAX_COMPLEXITY = "max_complexity"
    MAX_ARGUMENTS = "max_arguments"
    TYPE_CHECKING = "type_checking"
    BANDIT_SEVERITY = "bandit_severity"
    BANDIT_CONFIDENCE = "bandit_confidence"
    PYLINT_FAIL_UNDER = "pylint_fail_under"
    PATHS_FROM_STDIN = "paths_from_stdin"
    CHANGED_ONLY = "changed_only"
    DIFF_REF = "diff_ref"
    INCLUDE_UNTRACKED = "include_untracked"
    BASE_BRANCH = "base_branch"
    DIRS = "dirs"
    PATHS = "paths"
    EXCLUDE = "exclude"
    FILTERS = "filters"
    VERBOSE = "verbose"
    QUIET = "quiet"
    NO_COLOR = "no_color"
    NO_EMOJI = "no_emoji"
    OUTPUT_MODE = "output_mode"
    SHOW_PASSING = "show_passing"
    NO_STATS = "no_stats"
    ADVICE = "advice"
    PR_SUMMARY_OUT = "pr_summary_out"
    PR_SUMMARY_LIMIT = "pr_summary_limit"
    PR_SUMMARY_MIN_SEVERITY = "pr_summary_min_severity"
    PR_SUMMARY_TEMPLATE = "pr_summary_template"
    ONLY = "only"
    LANGUAGE = "language"
    FIX_ONLY = "fix_only"
    CHECK_ONLY = "check_only"
    BAIL = "bail"
    JOBS = "jobs"
    NO_CACHE = "no_cache"
    CACHE_DIR = "cache_dir"
    USE_LOCAL_LINTERS = "use_local_linters"
    LINE_LENGTH = "line_length"
    SQL_DIALECT = "sql_dialect"
    PYTHON_VERSION = "python_version"


FILTER_SPEC_SEPARATOR: Final[str] = ":"
FILTER_PATTERN_SEPARATOR: Final[str] = ";;"
FILTER_SPEC_FORMAT: Final[str] = "TOOL:regex"


def _build_default_tool_filters() -> dict[str, list[str]]:
    """Merge built-in, test, and catalog suppressions into filter defaults.

    Returns:
        dict[str, list[str]]: Mapping of tool identifiers to default filter
        patterns de-duplicated across all sources.
    """

    merged: dict[str, list[str]] = {
        tool: list(patterns) for tool, patterns in _BASE_TOOL_FILTERS.items()
    }
    for tool, patterns in flatten_test_suppressions().items():
        merged.setdefault(tool, []).extend(patterns)
    for tool, patterns in catalog_general_suppressions().items():
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


EnumValueT = TypeVar("EnumValueT", bound=Enum)


def build_config(options: LintOptions) -> Config:
    """Translate CLI option data into an executable configuration.

    Args:
        options: CLI options resolved from command-line arguments.

    Returns:
        Config: Concrete configuration instance prepared for execution.
    """

    project_root = options.root.resolve()
    loader = ConfigLoader.for_root(project_root)
    load_result = loader.load_with_trace(strict=options.strict_config)
    base_config = load_result.config

    baseline = base_config.snapshot_shared_knobs()

    file_cfg = _build_file_discovery(base_config.file_discovery, options, project_root)
    output_cfg = _build_output(base_config.output, options, project_root)
    execution_cfg = _build_execution(base_config.execution, options, project_root)
    execution_cfg = resolve_python_version(
        project_root,
        execution_cfg,
        cli_specified=LintOptionKey.PYTHON_VERSION.value in options.provided,
    )

    dedupe_cfg = base_config.dedupe.model_copy(deep=True)
    config_updates = {
        "file_discovery": file_cfg,
        "output": output_cfg,
        "execution": execution_cfg,
        "dedupe": dedupe_cfg,
        "severity_rules": list(base_config.severity_rules),
        "tool_settings": {
            tool: dict(settings) for tool, settings in base_config.tool_settings.items()
        },
    }
    config = base_config.model_copy(update=config_updates, deep=True)

    config = _apply_cli_overrides(config, options)
    config.apply_sensitivity_profile(cli_overrides=options.provided)
    config.apply_shared_defaults(override=True, baseline=baseline)
    return config


def _apply_cli_overrides(config: Config, options: LintOptions) -> Config:
    """Apply CLI-specified overrides onto the loaded configuration.

    Args:
        config: Baseline configuration loaded from disk.
        options: Structured CLI options supplied by the user.

    Returns:
        Config: Updated configuration reflecting CLI overrides.

    Raises:
        ValueError: If the CLI-provided override uses an unsupported token.
    """

    has_option = cast(
        Callable[[LintOptionKey], bool],
        partial(_is_option_provided, provided=options.provided),
    )

    severity_updates: dict[str, object] = {}
    complexity_updates: dict[str, int | None] = {}
    strictness_updates: dict[str, StrictnessLevel] = {}

    if has_option(LintOptionKey.SENSITIVITY) and options.sensitivity:
        severity_updates["sensitivity"] = _coerce_enum_value(
            options.sensitivity,
            SensitivityLevel,
            "--sensitivity",
        )
    if has_option(LintOptionKey.MAX_COMPLEXITY) and options.max_complexity is not None:
        complexity_updates["max_complexity"] = options.max_complexity
    if has_option(LintOptionKey.MAX_ARGUMENTS) and options.max_arguments is not None:
        complexity_updates["max_arguments"] = options.max_arguments
    if has_option(LintOptionKey.TYPE_CHECKING) and options.type_checking:
        strictness_updates["type_checking"] = _coerce_enum_value(
            options.type_checking,
            StrictnessLevel,
            "--type-checking",
        )
    if has_option(LintOptionKey.BANDIT_SEVERITY) and options.bandit_severity:
        severity_updates["bandit_level"] = _coerce_enum_value(
            options.bandit_severity,
            BanditLevel,
            "--bandit-severity",
        )
    if has_option(LintOptionKey.BANDIT_CONFIDENCE) and options.bandit_confidence:
        severity_updates["bandit_confidence"] = _coerce_enum_value(
            options.bandit_confidence,
            BanditConfidence,
            "--bandit-confidence",
        )
    if has_option(LintOptionKey.PYLINT_FAIL_UNDER) and options.pylint_fail_under is not None:
        severity_updates["pylint_fail_under"] = options.pylint_fail_under

    updates: dict[str, object] = {}
    if complexity_updates:
        updates["complexity"] = config.complexity.model_copy(update=complexity_updates)
    if strictness_updates:
        updates["strictness"] = config.strictness.model_copy(update=strictness_updates)
    if severity_updates:
        updates["severity"] = config.severity.model_copy(update=severity_updates)

    if updates:
        config = config.model_copy(update=updates)
    return config


def _is_option_provided(key: LintOptionKey, *, provided: set[str]) -> bool:
    """Return whether a specific CLI option has been explicitly provided.

    Args:
        key: The option identifier to test.
        provided: Collection of option labels supplied by the CLI parser.

    Returns:
        bool: ``True`` when the option was explicitly set.
    """

    return key.value in provided


def _coerce_enum_value(raw: str, enum_cls: type[EnumValueT], context: str) -> EnumValueT:
    """Translate a CLI token into a strongly typed enumeration value.

    Args:
        raw: Raw token provided by the CLI.
        enum_cls: Enumeration type expected by the configuration field.
        context: Human-friendly description used in error messages.

    Returns:
        EnumValueT: Enum member matching the provided token.

    Raises:
        ValueError: If the token does not align with the enumeration values.
    """

    candidate = raw.strip().lower()
    for member in enum_cls:
        if member.value == candidate:
            return member
    allowed = ", ".join(sorted(member.value for member in enum_cls))
    raise ValueError(f"{context} must be one of: {allowed}")


def _build_file_discovery(
    current: FileDiscoveryConfig,
    options: LintOptions,
    project_root: Path,
) -> FileDiscoveryConfig:
    """Construct the file discovery configuration with CLI overrides.

    Args:
        current: File discovery configuration loaded from disk.
        options: CLI options affecting file discovery behaviour.
        project_root: Project root directory used to resolve relative paths.

    Returns:
        FileDiscoveryConfig: Updated configuration reflecting CLI overrides.
    """

    provided = options.provided
    roots = _resolved_roots(current, project_root, options)
    explicit_files, boundaries = _resolved_explicit_files(
        current,
        options,
        project_root,
        roots,
    )
    excludes = _resolved_excludes(current, options, project_root)

    paths_from_stdin = _select_flag(
        options.paths_from_stdin,
        current.paths_from_stdin,
        LintOptionKey.PATHS_FROM_STDIN,
        provided,
    )
    changed_only = _select_flag(
        options.changed_only,
        current.changed_only,
        LintOptionKey.CHANGED_ONLY,
        provided,
    )
    diff_ref = _select_value(
        options.diff_ref,
        current.diff_ref,
        LintOptionKey.DIFF_REF,
        provided,
    )
    include_untracked = _select_flag(
        options.include_untracked,
        current.include_untracked,
        LintOptionKey.INCLUDE_UNTRACKED,
        provided,
    )
    base_branch = _select_value(
        options.base_branch,
        current.base_branch,
        LintOptionKey.BASE_BRANCH,
        provided,
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
    """Resolve root directories that should be scanned for files.

    Args:
        current: File discovery configuration sourced from disk.
        project_root: Absolute project root path.
        options: CLI options capable of augmenting root directories.

    Returns:
        list[Path]: Ordered list of unique root paths.
    """

    roots = shared_unique_paths(_ensure_abs(project_root, path) for path in current.roots)
    if project_root not in roots:
        roots.insert(0, project_root)

    if _is_option_provided(LintOptionKey.DIRS, provided=options.provided):
        resolved_dirs = (
            directory if directory.is_absolute() else (project_root / directory)
            for directory in options.dirs
        )
        roots.extend(path.resolve() for path in resolved_dirs)

    return shared_unique_paths(roots)


def _resolved_explicit_files(
    current: FileDiscoveryConfig,
    options: LintOptions,
    project_root: Path,
    roots: list[Path],
) -> tuple[list[Path], list[Path]]:
    """Resolve explicit files and directory boundaries supplied via CLI.

    Args:
        current: File discovery configuration containing persisted overrides.
        options: CLI options providing explicit file or directory selections.
        project_root: Absolute project root path.
        roots: Mutable list of active root directories.

    Returns:
        tuple[list[Path], list[Path]]: Explicit file paths and derived
        boundaries restricting discovery.
    """

    explicit_files: list[Path] = shared_existing_unique_paths(current.explicit_files)
    user_dirs: list[Path] = []
    user_files: list[Path] = []

    if _is_option_provided(LintOptionKey.PATHS, provided=options.provided):
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

    boundaries = shared_unique_paths(
        boundary
        for boundary in _derive_boundaries(user_dirs, user_files)
        if boundary
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
    """Filter root directories to those within supplied boundaries.

    Args:
        roots: Candidate root directories for discovery.
        boundaries: Boundary paths derived from CLI explicit selections.

    Returns:
        list[Path]: Filtered list of root directories constrained by
        boundaries, ensuring uniqueness.
    """

    matching = [path for path in roots if _is_within_any(path, boundaries)]
    if matching:
        merged = list(matching)
        merged.extend(path for path in boundaries if path not in matching and path.is_dir())
        return shared_unique_paths(merged)
    boundary_dirs = [path for path in boundaries if path.is_dir()]
    return shared_unique_paths(boundary_dirs)


def _derive_boundaries(user_dirs: Sequence[Path], user_files: Sequence[Path]) -> Iterable[Path]:
    """Yield discovery boundaries derived from explicit user selections.

    Args:
        user_dirs: Explicit directory paths provided via CLI options.
        user_files: Explicit file paths provided via CLI options.

    Yields:
        Iterable of parent directories constraining file discovery.
    """

    parents = [file_path.parent for file_path in user_files]
    for candidate in (*user_dirs, *parents):
        if candidate:
            yield candidate


def _resolved_excludes(
    current: FileDiscoveryConfig,
    options: LintOptions,
    project_root: Path,
) -> list[Path]:
    """Resolve excluded paths by combining defaults, config, and CLI input.

    Args:
        current: File discovery configuration loaded from disk.
        options: CLI options capable of introducing additional excludes.
        project_root: Project root directory used to resolve relative paths.

    Returns:
        list[Path]: Unique, absolute exclude paths.
    """

    excludes = shared_unique_paths(path.resolve() for path in current.excludes)
    for default_path in DEFAULT_EXCLUDES:
        resolved = _resolve_path(project_root, default_path).resolve()
        if resolved not in excludes:
            excludes.append(resolved)
    if _is_option_provided(LintOptionKey.EXCLUDE, provided=options.provided):
        for path in options.exclude:
            resolved = _resolve_path(project_root, path).resolve()
            if resolved not in excludes:
                excludes.append(resolved)
    if options.no_lint_tests:
        tests_path = _resolve_path(project_root, Path("tests")).resolve()
        if tests_path not in excludes:
            excludes.append(tests_path)
    return excludes


def _select_flag(candidate: bool, fallback: bool, key: LintOptionKey, provided: set[str]) -> bool:
    """Return the candidate flag when the CLI override is present.

    Args:
        candidate: Value sourced from CLI options.
        fallback: Existing configuration value used when no override exists.
        key: CLI option identifier associated with the candidate value.
        provided: Collection of CLI keys explicitly supplied by the user.

    Returns:
        bool: Selected flag value honouring the CLI override.
    """

    return candidate if key.value in provided else fallback


def _select_value(
    value: str | None,
    fallback: str | None,
    key: LintOptionKey,
    provided: set[str],
) -> str | None:
    """Return the candidate value when the CLI override is present.

    Args:
        value: Value supplied through CLI options.
        fallback: Existing configuration value when no override exists.
        key: CLI option identifier controlling override behaviour.
        provided: Collection of CLI keys explicitly supplied by the user.

    Returns:
        str | None: Selected value honouring CLI overrides.
    """

    return value if key.value in provided else fallback


def _build_output(current: OutputConfig, options: LintOptions, project_root: Path) -> OutputConfig:
    """Construct output configuration applying CLI overrides when present.

    Args:
        current: Output configuration loaded from disk.
        options: CLI options controlling output behaviour.
        project_root: Project root path used to resolve filesystem targets.

    Returns:
        OutputConfig: Updated output configuration reflecting CLI overrides.
    """

    provided = options.provided
    has_option = cast(
        Callable[[LintOptionKey], bool],
        partial(_is_option_provided, provided=provided),
    )

    tool_filters: ToolFilters = {
        tool: patterns.copy() for tool, patterns in DEFAULT_TOOL_FILTERS.items()
    }
    for tool, patterns in current.tool_filters.items():
        tool_filters.setdefault(tool, []).extend(patterns)
    if has_option(LintOptionKey.FILTERS):
        parsed = _parse_filters(options.filters)
        for tool, patterns in parsed.items():
            tool_filters.setdefault(tool, []).extend(patterns)
    normalised_filters: ToolFilters = {
        tool: list(dict.fromkeys(patterns)) for tool, patterns in tool_filters.items()
    }

    quiet_value = options.quiet if has_option(LintOptionKey.QUIET) else current.quiet

    show_passing_value = (
        options.show_passing if has_option(LintOptionKey.SHOW_PASSING) else current.show_passing
    )
    show_stats_value = (
        (not options.no_stats) if has_option(LintOptionKey.NO_STATS) else current.show_stats
    )
    if quiet_value:
        show_passing_value = False
        show_stats_value = False

    output_updates: dict[str, object | None] = {
        "tool_filters": normalised_filters,
        "verbose": (
            options.verbose if has_option(LintOptionKey.VERBOSE) else current.verbose
        ),
        "quiet": quiet_value,
        "color": (
            (not options.no_color)
            if has_option(LintOptionKey.NO_COLOR)
            else current.color
        ),
        "emoji": (
            (not options.no_emoji)
            if has_option(LintOptionKey.NO_EMOJI)
            else current.emoji
        ),
        "output": (
            _normalize_output_mode(options.output_mode)
            if has_option(LintOptionKey.OUTPUT_MODE)
            else current.output
        ),
        "show_passing": show_passing_value,
        "show_stats": show_stats_value,
        "advice": (
            options.advice if has_option(LintOptionKey.ADVICE) else current.advice
        ),
        "pr_summary_out": (
            _resolve_optional_path(project_root, options.pr_summary_out)
            if has_option(LintOptionKey.PR_SUMMARY_OUT)
            else current.pr_summary_out
        ),
        "pr_summary_limit": (
            options.pr_summary_limit
            if has_option(LintOptionKey.PR_SUMMARY_LIMIT)
            else current.pr_summary_limit
        ),
        "pr_summary_min_severity": (
            _normalize_min_severity(options.pr_summary_min_severity)
            if has_option(LintOptionKey.PR_SUMMARY_MIN_SEVERITY)
            else current.pr_summary_min_severity
        ),
        "pr_summary_template": (
            options.pr_summary_template
            if has_option(LintOptionKey.PR_SUMMARY_TEMPLATE)
            else current.pr_summary_template
        ),
    }

    return _model_clone(current, **output_updates)


def _build_execution(
    current: ExecutionConfig,
    options: LintOptions,
    project_root: Path,
) -> ExecutionConfig:
    """Construct execution configuration applying CLI overrides when present.

    Args:
        current: Execution configuration loaded from disk.
        options: CLI options controlling execution behaviour.
        project_root: Project root path used to resolve cache directories.

    Returns:
        ExecutionConfig: Updated execution configuration reflecting CLI
        overrides.
    """

    provided = options.provided
    has_option = cast(
        Callable[[LintOptionKey], bool],
        partial(_is_option_provided, provided=provided),
    )

    bail_value = options.bail if has_option(LintOptionKey.BAIL) else current.bail
    jobs_value = options.jobs if has_option(LintOptionKey.JOBS) else current.jobs
    if bail_value:
        jobs_value = 1

    execution_updates: dict[str, object | list[str] | Path | None] = {
        "only": (
            list(options.only)
            if has_option(LintOptionKey.ONLY)
            else list(current.only)
        ),
        "languages": (
            list(options.language)
            if has_option(LintOptionKey.LANGUAGE)
            else list(current.languages)
        ),
        "fix_only": (
            options.fix_only if has_option(LintOptionKey.FIX_ONLY) else current.fix_only
        ),
        "check_only": (
            options.check_only if has_option(LintOptionKey.CHECK_ONLY) else current.check_only
        ),
        "bail": bail_value,
        "jobs": jobs_value,
        "cache_enabled": (
            (not options.no_cache)
            if has_option(LintOptionKey.NO_CACHE)
            else current.cache_enabled
        ),
        "cache_dir": (
            _resolve_path(project_root, options.cache_dir).resolve()
            if has_option(LintOptionKey.CACHE_DIR)
            else current.cache_dir
        ),
        "use_local_linters": (
            options.use_local_linters
            if has_option(LintOptionKey.USE_LOCAL_LINTERS)
            else current.use_local_linters
        ),
        "line_length": (
            options.line_length
            if has_option(LintOptionKey.LINE_LENGTH)
            else current.line_length
        ),
        "sql_dialect": (
            options.sql_dialect
            if has_option(LintOptionKey.SQL_DIALECT)
            else current.sql_dialect
        ),
        "python_version": (
            options.python_version
            if has_option(LintOptionKey.PYTHON_VERSION)
            else current.python_version
        ),
    }

    return _model_clone(current, **execution_updates)


def _resolve_path(root: Path, path: Path) -> Path:
    """Resolve a potentially relative path against the project root.

    Args:
        root: Project root directory providing resolution context.
        path: Candidate path supplied by configuration or CLI options.

    Returns:
        Path: Absolute or root-relative path ensuring consistent resolution.
    """

    try:
        normalised = normalize_path(path, base_dir=root)
    except (ValueError, OSError):
        return path if path.is_absolute() else (root / path)
    if normalised.is_absolute():
        return normalised
    return root / normalised


def _resolve_optional_path(root: Path, path: Path | None) -> Path | None:
    """Resolve an optional path, preserving ``None`` when unspecified.

    Args:
        root: Project root directory providing resolution context.
        path: Optional candidate path supplied by configuration or CLI.

    Returns:
        Path | None: Resolved path when provided, otherwise ``None``.
    """

    if path is None:
        return None
    resolved = _resolve_path(root, path)
    try:
        return resolved.resolve()
    except OSError:
        return resolved.absolute()


def _ensure_abs(root: Path, path: Path) -> Path:
    """Ensure that a path is absolute, resolving relative values as needed.

    Args:
        root: Project root directory providing resolution context.
        path: Candidate path to normalise.

    Returns:
        Path: Absolute path resolved relative to ``root`` when necessary.
    """

    resolved = _resolve_path(root, path)
    try:
        return resolved.resolve()
    except OSError:
        return resolved.absolute()


def _is_within_any(path: Path, bounds: Iterable[Path]) -> bool:
    """Return whether ``path`` resides within any boundary path.

    Args:
        path: Candidate path to evaluate.
        bounds: Iterable of boundary directories.

    Returns:
        bool: ``True`` when the path is contained within a boundary.
    """

    for bound in bounds:
        try:
            path.relative_to(bound)
            return True
        except ValueError:
            continue
    return False


def _parse_filters(specs: Iterable[str]) -> ToolFilters:
    """Parse CLI filter specifications into a tool-to-pattern mapping.

    Args:
        specs: Iterable of ``TOOL:regex`` filter expressions supplied via CLI.

    Returns:
        ToolFilters: Mapping of tool identifiers to normalised regex patterns.

    Raises:
        ValueError: If a specification omits the required separator or the
        tool identifier is blank.
    """

    filters: ToolFilters = {tool: list(patterns) for tool, patterns in DEFAULT_TOOL_FILTERS.items()}
    for spec in specs:
        if FILTER_SPEC_SEPARATOR not in spec:
            raise ValueError(f"Invalid filter '{spec}'. Expected {FILTER_SPEC_FORMAT}")
        tool, expressions = spec.split(FILTER_SPEC_SEPARATOR, 1)
        tool_key = tool.strip()
        if not tool_key:
            raise ValueError(f"Invalid filter '{spec}'. Tool identifier cannot be empty")
        chunks = [
            chunk.strip()
            for chunk in expressions.split(FILTER_PATTERN_SEPARATOR)
            if chunk.strip()
        ]
        if not chunks:
            continue
        filters.setdefault(tool_key, []).extend(chunks)
    return filters


def _normalize_output_mode(value: str) -> OutputMode:
    """Validate and normalise the output mode CLI token.

    Args:
        value: CLI-provided output mode token.

    Returns:
        OutputMode: Canonical output mode string.

    Raises:
        ValueError: If the token does not match the allowed output modes.
    """

    normalized = value.lower()
    if normalized not in _ALLOWED_OUTPUT_MODES:
        raise ValueError(f"invalid output mode '{value}'")
    return cast("OutputMode", normalized)


def _normalize_min_severity(value: str) -> SummarySeverity:
    """Validate and normalise the PR summary minimum severity token.

    Args:
        value: CLI-provided severity token.

    Returns:
        SummarySeverity: Canonical severity literal.

    Raises:
        ValueError: If the token is not within the allowed severity values.
    """

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
    """Return a defensive copy of a Pydantic model applying updates.

    Args:
        instance: Source Pydantic model instance.
        **updates: Field updates applied to the cloned instance.

    Returns:
        ModelT: Cloned model instance containing the requested updates.
    """

    return cast("ModelT", instance.model_copy(update=updates, deep=True))
