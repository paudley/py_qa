# SPDX-License-Identifier: MIT
"""Shared models and Typer dependency factories for the lint CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal, cast

import typer

from .shared import Depends

StrictnessLiteral = Literal["lenient", "standard", "strict"]
BanditLevelLiteral = Literal["low", "medium", "high"]
SensitivityLiteral = Literal["low", "medium", "high", "maximum"]
OutputModeLiteral = Literal["concise", "pretty", "raw"]
PRSummarySeverityLiteral = Literal["error", "warning", "notice", "note"]
ProgressPhaseLiteral = Literal["start", "completed", "error"]

STRICTNESS_CHOICES: Final[tuple[StrictnessLiteral, ...]] = ("lenient", "standard", "strict")
BANDIT_LEVEL_CHOICES: Final[tuple[BanditLevelLiteral, ...]] = ("low", "medium", "high")
SENSITIVITY_CHOICES: Final[tuple[SensitivityLiteral, ...]] = (
    "low",
    "medium",
    "high",
    "maximum",
)
OUTPUT_MODE_CHOICES: Final[tuple[OutputModeLiteral, ...]] = ("concise", "pretty", "raw")
OUTPUT_MODE_CONCISE: Final[OutputModeLiteral] = "concise"
PR_SUMMARY_SEVERITIES: Final[tuple[PRSummarySeverityLiteral, ...]] = (
    "error",
    "warning",
    "notice",
    "note",
)
PROGRESS_EVENT_START: Final[ProgressPhaseLiteral] = "start"
PROGRESS_EVENT_COMPLETED: Final[ProgressPhaseLiteral] = "completed"

NORMAL_PRESET_HELP: Final[str] = (
    "Apply the built-in 'normal' lint preset "
    "(concise output, advice, no tests, local linters)."
)
FILTER_HELP: Final[str] = "Filter stdout/stderr from TOOL using regex (TOOL:pattern)."
OUTPUT_MODE_HELP: Final[str] = "Output mode: concise, pretty, or raw."
REPORT_JSON_HELP: Final[str] = "Write JSON report to the provided path."
SARIF_HELP: Final[str] = "Write SARIF 2.1.0 report to the provided path."
PR_SUMMARY_OUT_HELP: Final[str] = "Write a Markdown PR summary of diagnostics."
PR_SUMMARY_MIN_SEVERITY_HELP: Final[str] = (
    "Lowest severity for PR summary (error, warning, notice, note)."
)
PR_SUMMARY_TEMPLATE_HELP: Final[str] = "Custom format string for PR summary entries."
JOBS_HELP: Final[str] = (
    "Max parallel jobs (defaults to 75% of available CPU cores)."
)
CACHE_DIR_HELP: Final[str] = "Cache directory for tool results."
USE_LOCAL_LINTERS_HELP: Final[str] = (
    "Force vendored linters even if compatible system versions exist."
)
STRICT_CONFIG_HELP: Final[str] = (
    "Treat configuration warnings (unknown keys, etc.) as errors."
)
LINE_LENGTH_HELP: Final[str] = (
    "Global preferred maximum line length applied to supported tools."
)
MAX_COMPLEXITY_HELP: Final[str] = (
    "Override maximum cyclomatic complexity shared across supported tools."
)
MAX_ARGUMENTS_HELP: Final[str] = (
    "Override maximum function arguments shared across supported tools."
)
TYPE_CHECKING_HELP: Final[str] = (
    "Override type-checking strictness (lenient, standard, or strict)."
)
BANDIT_SEVERITY_HELP: Final[str] = (
    "Override Bandit's minimum severity (low, medium, high)."
)
BANDIT_CONFIDENCE_HELP: Final[str] = (
    "Override Bandit's minimum confidence (low, medium, high)."
)
PYLINT_FAIL_UNDER_HELP: Final[str] = "Override pylint fail-under score (0-10)."
SENSITIVITY_HELP: Final[str] = (
    "Overall sensitivity (low, medium, high, maximum) to cascade severity tweaks."
)
SQL_DIALECT_HELP: Final[str] = (
    "Default SQL dialect for dialect-aware tools (e.g. sqlfluff)."
)
TOOL_INFO_HELP: Final[str] = "Display detailed information for TOOL and exit."
FETCH_ALL_TOOLS_HELP: Final[str] = (
    "Download or prepare runtimes for every registered tool and exit."
)
ADVICE_HELP: Final[str] = (
    "Provide SOLID-aligned refactoring suggestions alongside diagnostics."
)
VALIDATE_SCHEMA_HELP: Final[str] = (
    "Validate catalog definitions against bundled schemas and exit."
)
PYTHON_VERSION_HELP: Final[str] = (
    "Override the Python interpreter version advertised to tools (e.g. 3.12)."
)


@dataclass(slots=True)
class LintPathParams:
    """Capture filesystem path arguments supplied to the CLI."""

    paths: list[Path]
    root: Path
    paths_from_stdin: bool
    dirs: list[Path]
    exclude: list[Path]


@dataclass(slots=True)
class LintGitParams:
    """Represent git-related discovery toggles."""

    changed_only: bool
    diff_ref: str
    include_untracked: bool
    base_branch: str | None
    no_lint_tests: bool


@dataclass(slots=True)
class LintSelectionParams:
    """Capture tool selection filters and mode switches."""

    filters: list[str]
    only: list[str]
    language: list[str]
    fix_only: bool
    check_only: bool


@dataclass(slots=True)
class LintExecutionRuntimeParams:
    """Runtime tuning controls for orchestrator execution."""

    jobs: int | None
    bail: bool
    no_cache: bool
    cache_dir: Path
    use_local_linters: bool
    strict_config: bool


@dataclass(slots=True)
class LintOutputParams:
    """Rendering preferences for user-facing output."""

    verbose: bool
    quiet: bool
    no_color: bool
    no_emoji: bool
    output_mode: OutputModeLiteral


@dataclass(slots=True)
class LintReportingParams:
    """Reporting targets selected by the user."""

    show_passing: bool
    no_stats: bool
    report_json: Path | None
    sarif_out: Path | None
    pr_summary_out: Path | None


@dataclass(slots=True)
class LintSummaryParams:
    """Parameters controlling PR summary generation."""

    pr_summary_limit: int
    pr_summary_min_severity: PRSummarySeverityLiteral
    pr_summary_template: str
    advice: bool


@dataclass(slots=True)
class LintOverrideParams:
    """Shared override knobs applied to tool configurations."""

    line_length: int
    sql_dialect: str
    max_complexity: int | None
    max_arguments: int | None
    type_checking: StrictnessLiteral | None
    python_version: str | None


@dataclass(slots=True)
class LintSeverityParams:
    """Severity-oriented override values for diagnostics."""

    bandit_severity: BanditLevelLiteral | None
    bandit_confidence: BanditLevelLiteral | None
    pylint_fail_under: float | None
    sensitivity: SensitivityLiteral | None


@dataclass(slots=True)
class LintMetaParams:
    """Meta toggles that alter command execution flow."""

    doctor: bool
    tool_info: str | None
    fetch_all_tools: bool
    validate_schema: bool
    normal: bool


@dataclass(slots=True)
class LintTargetGroup:
    """Group path discovery parameters with git selectors."""

    path: LintPathParams
    git: LintGitParams


@dataclass(slots=True)
class LintExecutionGroup:
    """Group tool selection and runtime execution options."""

    selection: LintSelectionParams
    runtime: LintExecutionRuntimeParams


@dataclass(slots=True)
class LintOutputGroup:
    """Combine rendering, reporting, and summary preferences."""

    rendering: LintOutputParams
    reporting: LintReportingParams
    summary: LintSummaryParams


@dataclass(slots=True)
class LintAdvancedGroup:
    """Aggregate advanced overrides and meta controls."""

    overrides: LintOverrideParams
    severity: LintSeverityParams
    meta: LintMetaParams


@dataclass(slots=True)
class LintCLIInputs:
    """Top-level container for structured CLI inputs."""

    targets: LintTargetGroup
    execution: LintExecutionGroup
    output: LintOutputGroup
    advanced: LintAdvancedGroup


@dataclass(slots=True)
class LintOutputArtifacts:
    """Filesystem artifacts generated by the lint command."""

    report_json: Path | None
    sarif_out: Path | None
    pr_summary_out: Path | None


@dataclass(slots=True)
class LintDisplayOptions:
    """Capture console toggles derived from CLI output flags."""

    no_emoji: bool
    quiet: bool
    verbose: bool


PathArgument = Annotated[
    list[Path] | None,
    typer.Argument(
        None,
        metavar="[PATH]",
        help="Specific files or directories to lint.",
    ),
]
RootOption = Annotated[
    Path,
    typer.Option(
        Path.cwd(),
        "--root",
        "-r",
        help="Project root.",
    ),
]


def _coerce_choice(value: str, *, option_name: str, choices: tuple[str, ...]) -> str:
    """Lower-case *value* and ensure it belongs to *choices*."""

    normalized = value.lower()
    if normalized not in choices:
        allowed = ", ".join(choices)
        raise typer.BadParameter(f"{option_name} must be one of: {allowed}")
    return normalized


def _coerce_output_mode(value: str) -> OutputModeLiteral:
    coerced = _coerce_choice(value, option_name="--output", choices=OUTPUT_MODE_CHOICES)
    return cast(OutputModeLiteral, coerced)


def _coerce_optional_strictness(value: str | None) -> StrictnessLiteral | None:
    if value is None:
        return None
    coerced = _coerce_choice(value, option_name="--type-checking", choices=STRICTNESS_CHOICES)
    return cast(StrictnessLiteral, coerced)


def _coerce_optional_bandit(value: str | None, *, option_name: str) -> BanditLevelLiteral | None:
    if value is None:
        return None
    coerced = _coerce_choice(value, option_name=option_name, choices=BANDIT_LEVEL_CHOICES)
    return cast(BanditLevelLiteral, coerced)


def _coerce_optional_sensitivity(value: str | None) -> SensitivityLiteral | None:
    if value is None:
        return None
    coerced = _coerce_choice(value, option_name="--sensitivity", choices=SENSITIVITY_CHOICES)
    return cast(SensitivityLiteral, coerced)


def _coerce_pr_summary_severity(value: str) -> PRSummarySeverityLiteral:
    coerced = _coerce_choice(
        value,
        option_name="--pr-summary-min-severity",
        choices=PR_SUMMARY_SEVERITIES,
    )
    return cast(PRSummarySeverityLiteral, coerced)


# Dependency factories -----------------------------------------------------------------


def _path_params_dependency(
    paths: PathArgument,
    root: RootOption,
    paths_from_stdin: Annotated[
        bool,
        typer.Option(False, help="Read file paths from stdin."),
    ],
    dirs: Annotated[
        list[Path],
        typer.Option([], "--dir", help="Add directory to discovery roots (repeatable)."),
    ],
    exclude: Annotated[
        list[Path],
        typer.Option([], help="Exclude specific paths or globs."),
    ],
) -> LintPathParams:
    return LintPathParams(
        paths=list(paths or []),
        root=root,
        paths_from_stdin=paths_from_stdin,
        dirs=list(dirs),
        exclude=list(exclude),
    )


def _git_params_dependency(
    changed_only: Annotated[
        bool,
        typer.Option(False, help="Limit to files changed according to git."),
    ],
    diff_ref: Annotated[
        str,
        typer.Option("HEAD", help="Git ref for change detection."),
    ],
    include_untracked: Annotated[
        bool,
        typer.Option(True, help="Include untracked files during git discovery."),
    ],
    base_branch: Annotated[
        str | None,
        typer.Option(None, help="Base branch for merge-base diffing."),
    ],
    no_lint_tests: Annotated[
        bool,
        typer.Option(
            False,
            "--no-lint-tests",
            help="Exclude paths containing 'tests' from linting.",
        ),
    ],
) -> LintGitParams:
    return LintGitParams(
        changed_only=changed_only,
        diff_ref=diff_ref,
        include_untracked=include_untracked,
        base_branch=base_branch,
        no_lint_tests=no_lint_tests,
    )


def _selection_params_dependency(
    filters: Annotated[
        list[str],
        typer.Option([], "--filter", help=FILTER_HELP),
    ],
    only: Annotated[list[str], typer.Option([], help="Run only the selected tool(s).")],
    language: Annotated[list[str], typer.Option([], help="Filter tools by language.")],
    fix_only: Annotated[bool, typer.Option(False, help="Run only fix-capable actions.")],
    check_only: Annotated[bool, typer.Option(False, help="Run only check actions.")],
) -> LintSelectionParams:
    return LintSelectionParams(
        filters=list(filters),
        only=list(only),
        language=list(language),
        fix_only=fix_only,
        check_only=check_only,
    )


def _execution_runtime_dependency(
    jobs: Annotated[
        int | None,
        typer.Option(None, "--jobs", "-j", min=1, help=JOBS_HELP),
    ],
    bail: Annotated[bool, typer.Option(False, "--bail", help="Exit on first tool failure.")],
    no_cache: Annotated[bool, typer.Option(False, help="Disable on-disk result caching.")],
    cache_dir: Annotated[
        Path,
        typer.Option(Path(".lint-cache"), "--cache-dir", help=CACHE_DIR_HELP),
    ],
    use_local_linters: Annotated[
        bool,
        typer.Option(False, "--use-local-linters", help=USE_LOCAL_LINTERS_HELP),
    ],
    strict_config: Annotated[
        bool,
        typer.Option(False, "--strict-config", help=STRICT_CONFIG_HELP),
    ],
) -> LintExecutionRuntimeParams:
    return LintExecutionRuntimeParams(
        jobs=jobs,
        bail=bail,
        no_cache=no_cache,
        cache_dir=cache_dir,
        use_local_linters=use_local_linters,
        strict_config=strict_config,
    )


def _output_params_dependency(
    verbose: Annotated[bool, typer.Option(False, help="Verbose output.")],
    quiet: Annotated[bool, typer.Option(False, "--quiet", "-q", help="Minimal output.")],
    no_color: Annotated[bool, typer.Option(False, help="Disable ANSI colour output.")],
    no_emoji: Annotated[bool, typer.Option(False, help="Disable emoji output.")],
    output_mode: Annotated[
        str,
        typer.Option(OUTPUT_MODE_CONCISE, "--output", help=OUTPUT_MODE_HELP),
    ],
) -> LintOutputParams:
    return LintOutputParams(
        verbose=verbose,
        quiet=quiet,
        no_color=no_color,
        no_emoji=no_emoji,
        output_mode=_coerce_output_mode(output_mode),
    )


def _reporting_params_dependency(
    show_passing: Annotated[
        bool,
        typer.Option(False, help="Include successful diagnostics in output."),
    ],
    no_stats: Annotated[
        bool,
        typer.Option(False, help="Suppress summary statistics."),
    ],
    report_json: Annotated[Path | None, typer.Option(None, help=REPORT_JSON_HELP)],
    sarif_out: Annotated[Path | None, typer.Option(None, help=SARIF_HELP)],
    pr_summary_out: Annotated[Path | None, typer.Option(None, help=PR_SUMMARY_OUT_HELP)],
) -> LintReportingParams:
    return LintReportingParams(
        show_passing=show_passing,
        no_stats=no_stats,
        report_json=report_json,
        sarif_out=sarif_out,
        pr_summary_out=pr_summary_out,
    )


def _summary_params_dependency(
    pr_summary_limit: Annotated[
        int,
        typer.Option(100, "--pr-summary-limit", help="Maximum diagnostics in PR summary."),
    ],
    pr_summary_min_severity: Annotated[
        str,
        typer.Option("warning", "--pr-summary-min-severity", help=PR_SUMMARY_MIN_SEVERITY_HELP),
    ],
    pr_summary_template: Annotated[
        str,
        typer.Option(
            "- **{severity}** `{tool}` {message} ({location})",
            "--pr-summary-template",
            help=PR_SUMMARY_TEMPLATE_HELP,
        ),
    ],
    advice: Annotated[bool, typer.Option(False, "--advice", help=ADVICE_HELP)],
) -> LintSummaryParams:
    return LintSummaryParams(
        pr_summary_limit=pr_summary_limit,
        pr_summary_min_severity=_coerce_pr_summary_severity(pr_summary_min_severity),
        pr_summary_template=pr_summary_template,
        advice=advice,
    )


def _override_params_dependency(
    line_length: Annotated[int, typer.Option(120, "--line-length", help=LINE_LENGTH_HELP)],
    sql_dialect: Annotated[str, typer.Option("postgresql", "--sql-dialect", help=SQL_DIALECT_HELP)],
    max_complexity: Annotated[
        int | None,
        typer.Option(None, "--max-complexity", min=1, help=MAX_COMPLEXITY_HELP),
    ],
    max_arguments: Annotated[
        int | None,
        typer.Option(None, "--max-arguments", min=1, help=MAX_ARGUMENTS_HELP),
    ],
    type_checking: Annotated[
        str | None,
        typer.Option(
            None,
            "--type-checking",
            case_sensitive=False,
            help=TYPE_CHECKING_HELP,
        ),
    ],
    python_version: Annotated[
        str | None,
        typer.Option(
            None,
            "--python-version",
            help=PYTHON_VERSION_HELP,
        ),
    ],
) -> LintOverrideParams:
    normalized_python_version = python_version.strip() if python_version else None

    return LintOverrideParams(
        line_length=line_length,
        sql_dialect=sql_dialect,
        max_complexity=max_complexity,
        max_arguments=max_arguments,
        type_checking=_coerce_optional_strictness(type_checking),
        python_version=normalized_python_version,
    )


def _severity_params_dependency(
    bandit_severity: Annotated[
        str | None,
        typer.Option(
            None,
            "--bandit-severity",
            case_sensitive=False,
            help=BANDIT_SEVERITY_HELP,
        ),
    ],
    bandit_confidence: Annotated[
        str | None,
        typer.Option(
            None,
            "--bandit-confidence",
            case_sensitive=False,
            help=BANDIT_CONFIDENCE_HELP,
        ),
    ],
    pylint_fail_under: Annotated[
        float | None,
        typer.Option(None, "--pylint-fail-under", help=PYLINT_FAIL_UNDER_HELP),
    ],
    sensitivity: Annotated[
        str | None,
        typer.Option(
            None,
            "--sensitivity",
            case_sensitive=False,
            help=SENSITIVITY_HELP,
        ),
    ],
) -> LintSeverityParams:
    return LintSeverityParams(
        bandit_severity=_coerce_optional_bandit(
            bandit_severity,
            option_name="--bandit-severity",
        ),
        bandit_confidence=_coerce_optional_bandit(
            bandit_confidence,
            option_name="--bandit-confidence",
        ),
        pylint_fail_under=pylint_fail_under,
        sensitivity=_coerce_optional_sensitivity(sensitivity),
    )


def _meta_params_dependency(
    doctor: Annotated[
        bool,
        typer.Option(False, "--doctor", help="Run environment diagnostics and exit."),
    ],
    tool_info: Annotated[
        str | None,
        typer.Option(None, "--tool-info", metavar="TOOL", help=TOOL_INFO_HELP),
    ],
    fetch_all_tools: Annotated[
        bool,
        typer.Option(False, "--fetch-all-tools", help=FETCH_ALL_TOOLS_HELP),
    ],
    validate_schema: Annotated[
        bool,
        typer.Option(False, "--validate-schema", help=VALIDATE_SCHEMA_HELP),
    ],
    normal: Annotated[
        bool,
        typer.Option(False, "-n", "--normal", help=NORMAL_PRESET_HELP),
    ],
) -> LintMetaParams:
    return LintMetaParams(
        doctor=doctor,
        tool_info=tool_info,
        fetch_all_tools=fetch_all_tools,
        validate_schema=validate_schema,
        normal=normal,
    )


def _build_target_group(
    path_params: Annotated[LintPathParams, Depends(_path_params_dependency)],
    git_params: Annotated[LintGitParams, Depends(_git_params_dependency)],
) -> LintTargetGroup:
    return LintTargetGroup(path=path_params, git=git_params)


def _build_execution_group(
    selection: Annotated[LintSelectionParams, Depends(_selection_params_dependency)],
    runtime: Annotated[LintExecutionRuntimeParams, Depends(_execution_runtime_dependency)],
) -> LintExecutionGroup:
    return LintExecutionGroup(selection=selection, runtime=runtime)


def _build_output_group(
    output_params: Annotated[LintOutputParams, Depends(_output_params_dependency)],
    reporting_params: Annotated[LintReportingParams, Depends(_reporting_params_dependency)],
    summary_params: Annotated[LintSummaryParams, Depends(_summary_params_dependency)],
) -> LintOutputGroup:
    return LintOutputGroup(
        rendering=output_params,
        reporting=reporting_params,
        summary=summary_params,
    )


def _build_advanced_group(
    overrides: Annotated[LintOverrideParams, Depends(_override_params_dependency)],
    severity: Annotated[LintSeverityParams, Depends(_severity_params_dependency)],
    meta: Annotated[LintMetaParams, Depends(_meta_params_dependency)],
) -> LintAdvancedGroup:
    return LintAdvancedGroup(
        overrides=overrides,
        severity=severity,
        meta=meta,
    )


def _build_lint_cli_inputs(
    targets: Annotated[LintTargetGroup, Depends(_build_target_group)],
    execution: Annotated[LintExecutionGroup, Depends(_build_execution_group)],
    output: Annotated[LintOutputGroup, Depends(_build_output_group)],
    advanced: Annotated[LintAdvancedGroup, Depends(_build_advanced_group)],
) -> LintCLIInputs:
    return LintCLIInputs(
        targets=targets,
        execution=execution,
        output=output,
        advanced=advanced,
    )


__all__ = [
    "ADVICE_HELP",
    "BANDIT_CONFIDENCE_HELP",
    "BANDIT_LEVEL_CHOICES",
    "BANDIT_SEVERITY_HELP",
    "CACHE_DIR_HELP",
    "FETCH_ALL_TOOLS_HELP",
    "FILTER_HELP",
    "JOBS_HELP",
    "LINE_LENGTH_HELP",
    "LintAdvancedGroup",
    "LintCLIInputs",
    "LintDisplayOptions",
    "LintExecutionGroup",
    "LintExecutionRuntimeParams",
    "LintGitParams",
    "LintMetaParams",
    "LintOutputArtifacts",
    "LintOutputGroup",
    "LintOutputParams",
    "LintPathParams",
    "LintReportingParams",
    "LintSelectionParams",
    "LintSeverityParams",
    "LintSummaryParams",
    "PathArgument",
    "RootOption",
    "MAX_ARGUMENTS_HELP",
    "MAX_COMPLEXITY_HELP",
    "NORMAL_PRESET_HELP",
    "OUTPUT_MODE_CHOICES",
    "OUTPUT_MODE_CONCISE",
    "OUTPUT_MODE_HELP",
    "PYTHON_VERSION_HELP",
    "PR_SUMMARY_MIN_SEVERITY_HELP",
    "PR_SUMMARY_OUT_HELP",
    "PR_SUMMARY_SEVERITIES",
    "PR_SUMMARY_TEMPLATE_HELP",
    "PROGRESS_EVENT_COMPLETED",
    "PROGRESS_EVENT_START",
    "ProgressPhaseLiteral",
    "PYLINT_FAIL_UNDER_HELP",
    "REPORT_JSON_HELP",
    "SENSITIVITY_CHOICES",
    "SENSITIVITY_HELP",
    "STRICTNESS_CHOICES",
    "STRICT_CONFIG_HELP",
    "StrictnessLiteral",
    "TOOL_INFO_HELP",
    "TYPE_CHECKING_HELP",
    "USE_LOCAL_LINTERS_HELP",
    "VALIDATE_SCHEMA_HELP",
    "_build_advanced_group",
    "_build_execution_group",
    "_build_lint_cli_inputs",
    "_build_output_group",
    "_build_target_group",
    "_coerce_optional_bandit",
    "_coerce_optional_sensitivity",
    "_coerce_optional_strictness",
    "_coerce_output_mode",
    "_git_params_dependency",
    "_meta_params_dependency",
    "_output_params_dependency",
    "_override_params_dependency",
    "_path_params_dependency",
    "_reporting_params_dependency",
    "_selection_params_dependency",
    "_severity_params_dependency",
    "_summary_params_dependency",
    "BanditLevelLiteral",
]
