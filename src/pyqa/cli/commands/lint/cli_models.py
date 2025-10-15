# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Shared models and Typer dependency factories for the lint CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, cast

import typer

from ...core.lint_literals import StrictnessLiteral
from ...core.shared import Depends
from ..update.models import ROOT_OPTION as UPDATE_ROOT_OPTION
from .literals import (
    BANDIT_LEVEL_CHOICES,
    OUTPUT_MODE_CHOICES,
    OUTPUT_MODE_CONCISE,
    PR_SUMMARY_SEVERITIES,
    SENSITIVITY_CHOICES,
    STRICTNESS_CHOICES,
    BanditLevelLiteral,
    OutputModeLiteral,
    PRSummarySeverityLiteral,
    SensitivityLiteral,
)
from .params import (
    LintAdvancedGroup,
    LintCLIInputs,
    LintExecutionGroup,
    LintExecutionRuntimeParams,
    LintGitParams,
    LintMetaParams,
    LintOutputGroup,
    LintOutputParams,
    LintOverrideParams,
    LintPathParams,
    LintReportingParams,
    LintSelectionParams,
    LintSeverityParams,
    LintSummaryParams,
    LintTargetGroup,
    MetaActionParams,
    MetaAnalysisChecks,
    MetaRuntimeChecks,
    OverrideFormattingParams,
    OverrideStrictnessParams,
    OverrideThresholdParams,
    RuntimeCacheParams,
    RuntimeConcurrencyParams,
)

NORMAL_PRESET_HELP: Final[str] = (
    "Apply the built-in 'normal' lint preset (concise output, advice, no tests, local linters)."
)
EXPLAIN_TOOLS_HELP: Final[str] = "Show the tool selection plan with reasons and exit."
DOCSTRINGS_HELP: Final[str] = "Run the internal docstring quality linter and exit."
SUPPRESSIONS_HELP: Final[str] = "Run the internal suppression checker and exit."
TYPING_HELP: Final[str] = "Run the strict typing checker and exit."
MISSING_HELP: Final[str] = "Run the missing functionality detector and exit."
CLOSURES_HELP: Final[str] = "Run the closure/partial usage checker and exit."
SIGNATURES_HELP: Final[str] = "Run the function signature width checker and exit."
CACHE_HELP: Final[str] = "Run the functools cache usage checker and exit."
PYQA_RULES_HELP: Final[str] = "Enable pyqa-specific lint rules even when running outside the pyqa repository."
CHECK_INTERFACES_HELP: Final[str] = "Run the pyqa interface enforcement linter and exit."
CHECK_DI_HELP: Final[str] = "Run the dependency-injection guardrails linter and exit."
CHECK_MODULE_DOCS_HELP: Final[str] = "Validate required MODULE.md documentation files and exit."
PYQA_PYTHON_HYGIENE_HELP: Final[str] = "Run the pyqa-specific hygiene checks (SystemExit and print guards) and exit."
SHOW_VALID_SUPPRESSIONS_HELP: Final[str] = "Display validated suppressions with their justifications."
LICENSE_HEADER_HELP: Final[str] = "Run the license header compliance checker and exit."
COPYRIGHT_HELP: Final[str] = "Run the copyright notice consistency checker and exit."
PYTHON_HYGIENE_HELP: Final[str] = "Run the Python hygiene checker (debug breakpoints, bare excepts) and exit."
FILE_SIZE_HELP: Final[str] = "Run the file size threshold checker and exit."
SCHEMA_SYNC_HELP: Final[str] = "Run the pyqa schema synchronisation checker and exit."
VALUE_TYPES_GENERAL_HELP: Final[str] = "Recommend dunder methods for value-type classes using Tree-sitter heuristics."
FILTER_HELP: Final[str] = "Filter stdout/stderr from TOOL using regex (TOOL:pattern)."
OUTPUT_MODE_HELP: Final[str] = "Output mode: concise, pretty, or raw."
REPORT_JSON_HELP: Final[str] = "Write JSON report to the provided path."
SARIF_HELP: Final[str] = "Write SARIF 2.1.0 report to the provided path."
PR_SUMMARY_OUT_HELP: Final[str] = "Write a Markdown PR summary of diagnostics."
PR_SUMMARY_MIN_SEVERITY_HELP: Final[str] = "Lowest severity for PR summary (error, warning, notice, note)."
PR_SUMMARY_TEMPLATE_HELP: Final[str] = "Custom format string for PR summary entries."
JOBS_HELP: Final[str] = "Max parallel jobs (defaults to 75% of available CPU cores)."
CACHE_DIR_HELP: Final[str] = "Cache directory for tool results."
USE_LOCAL_LINTERS_HELP: Final[str] = "Force vendored linters even if compatible system versions exist."
STRICT_CONFIG_HELP: Final[str] = "Treat configuration warnings (unknown keys, etc.) as errors."
LINE_LENGTH_HELP: Final[str] = "Global preferred maximum line length applied to supported tools."
MAX_COMPLEXITY_HELP: Final[str] = "Override maximum cyclomatic complexity shared across supported tools."
MAX_ARGUMENTS_HELP: Final[str] = "Override maximum function arguments shared across supported tools."
TYPE_CHECKING_HELP: Final[str] = "Override type-checking strictness (lenient, standard, or strict)."
BANDIT_SEVERITY_HELP: Final[str] = "Override Bandit's minimum severity (low, medium, high)."
BANDIT_CONFIDENCE_HELP: Final[str] = "Override Bandit's minimum confidence (low, medium, high)."
PYLINT_FAIL_UNDER_HELP: Final[str] = "Override pylint fail-under score (0-10)."
SENSITIVITY_HELP: Final[str] = "Overall sensitivity (low, medium, high, maximum) to cascade severity tweaks."
SQL_DIALECT_HELP: Final[str] = "Default SQL dialect for dialect-aware tools (e.g. sqlfluff)."
TOOL_INFO_HELP: Final[str] = "Display detailed information for TOOL and exit."
FETCH_ALL_TOOLS_HELP: Final[str] = "Download or prepare runtimes for every registered tool and exit."
ADVICE_HELP: Final[str] = "Provide SOLID-aligned refactoring suggestions alongside diagnostics."
VALIDATE_SCHEMA_HELP: Final[str] = "Validate catalog definitions against bundled schemas and exit."
PYTHON_VERSION_HELP: Final[str] = "Override the Python interpreter version advertised to tools (e.g. 3.12)."


@dataclass(slots=True)
class LintDisplayOptions:
    """Capture console toggles derived from CLI output flags."""

    no_emoji: bool
    quiet: bool
    verbose: bool
    debug: bool


@dataclass(slots=True)
class LintOutputToggles:
    """Boolean toggles controlling stdout rendering preferences."""

    verbose: bool
    quiet: bool
    no_color: bool
    no_emoji: bool
    debug: bool


@dataclass(slots=True)
class MetaActionToggleParams:
    """Encapsulate CLI meta-action toggles."""

    doctor: bool
    fetch_all_tools: bool
    validate_schema: bool
    normal: bool
    explain_tools: bool


@dataclass(slots=True)
class MetaActionInfo:
    """Hold optional meta-action arguments."""

    tool_info: str | None


@dataclass(slots=True)
class RuntimeCoreChecks:
    """Toggle set for core runtime lint checks."""

    check_closures: bool
    check_signatures: bool
    check_cache_usage: bool
    check_value_types: bool
    check_value_types_general: bool


@dataclass(slots=True)
class RuntimeInterfaceChecks:
    """Toggle set for interface-driven runtime checks."""

    check_interfaces: bool
    check_di: bool
    check_module_docs: bool
    check_pyqa_python_hygiene: bool


@dataclass(slots=True)
class RuntimePolicyChecks:
    """Toggle set for compliance and hygiene-related runtime checks."""

    show_valid_suppressions: bool
    check_license_header: bool
    check_copyright: bool
    check_python_hygiene: bool


@dataclass(slots=True)
class RuntimeAdditionalChecks:
    """Toggle set for advanced runtime verifications."""

    check_file_size: bool
    check_schema_sync: bool
    pyqa_rules: bool


PathArgument = Annotated[
    list[Path] | None,
    typer.Argument(
        None,
        metavar="[PATH]",
        help="Specific files or directories to lint.",
    ),
]
RootOption = UPDATE_ROOT_OPTION


def _coerce_choice(value: str, *, option_name: str, choices: tuple[str, ...]) -> str:
    """Normalise a string option and validate membership.

    Args:
        value: Raw user-supplied value to coerce.
        option_name: CLI option name used to build error messages.
        choices: Allowed choices for the option.

    Returns:
        str: Lower-cased value guaranteed to exist within ``choices``.

    Raises:
        typer.BadParameter: If ``value`` is not present in ``choices``.
    """

    normalized = value.lower()
    if normalized not in choices:
        allowed = ", ".join(choices)
        raise typer.BadParameter(f"{option_name} must be one of: {allowed}")
    return normalized


def _coerce_output_mode(value: str) -> OutputModeLiteral:
    """Return a validated output mode literal.

    Args:
        value: Raw output mode supplied via the CLI.

    Returns:
        OutputModeLiteral: Normalised output mode value.

    Raises:
        typer.BadParameter: If ``value`` does not map to a permitted mode.
    """

    coerced = _coerce_choice(value, option_name="--output", choices=OUTPUT_MODE_CHOICES)
    return cast(OutputModeLiteral, coerced)


def _coerce_optional_strictness(value: str | None) -> StrictnessLiteral | None:
    """Return a validated strictness literal when supplied.

    Args:
        value: Optional strictness value obtained from CLI flags.

    Returns:
        StrictnessLiteral | None: Normalised strictness or ``None`` when not
        provided.

    Raises:
        typer.BadParameter: If ``value`` falls outside the allowed set.
    """

    if value is None:
        return None
    coerced = _coerce_choice(value, option_name="--type-checking", choices=STRICTNESS_CHOICES)
    return cast(StrictnessLiteral, coerced)


def _coerce_optional_bandit(value: str | None, *, option_name: str) -> BanditLevelLiteral | None:
    """Return a validated Bandit level literal when supplied.

    Args:
        value: Optional Bandit level provided by the user.
        option_name: CLI option name used for error messaging.

    Returns:
        BanditLevelLiteral | None: Normalised severity or confidence value.

    Raises:
        typer.BadParameter: If ``value`` does not belong to the allowed set.
    """

    if value is None:
        return None
    coerced = _coerce_choice(value, option_name=option_name, choices=BANDIT_LEVEL_CHOICES)
    return cast(BanditLevelLiteral, coerced)


def _coerce_optional_sensitivity(value: str | None) -> SensitivityLiteral | None:
    """Return a validated sensitivity literal when supplied.

    Args:
        value: Optional sensitivity value provided via CLI arguments.

    Returns:
        SensitivityLiteral | None: Normalised sensitivity or ``None`` if not
        provided.

    Raises:
        typer.BadParameter: If ``value`` is outside the allowed set.
    """

    if value is None:
        return None
    coerced = _coerce_choice(value, option_name="--sensitivity", choices=SENSITIVITY_CHOICES)
    return cast(SensitivityLiteral, coerced)


def _coerce_pr_summary_severity(value: str) -> PRSummarySeverityLiteral:
    """Return a normalised PR summary severity literal.

    Args:
        value: Raw severity supplied on the CLI.

    Returns:
        PRSummarySeverityLiteral: Normalised severity literal.

    Raises:
        typer.BadParameter: If ``value`` is not one of the permitted severities.
    """

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
    """Return normalised filesystem parameters derived from CLI input.

    Args:
        paths: Optional positional path arguments.
        root: Repository root option supplied via CLI.
        paths_from_stdin: Flag indicating whether paths originate from stdin.
        dirs: Additional directory discovery roots.
        exclude: Explicit paths or globs to exclude from discovery.

    Returns:
        LintPathParams: Structured path parameters consumed by lint options.
    """

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
    """Return git-related discovery parameters derived from CLI input.

    Args:
        changed_only: Whether to limit discovery to changed files.
        diff_ref: Git reference used for change detection.
        include_untracked: Whether to include untracked files.
        base_branch: Base branch used to compute merge-base diffs.
        no_lint_tests: Flag indicating whether test directories are excluded.

    Returns:
        LintGitParams: Structured git discovery parameters.
    """

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
    """Return structured selection parameters based on CLI filters.

    Args:
        filters: Regex filters applied to tool output.
        only: Explicit tool selection overrides.
        language: Languages used to restrict tool execution.
        fix_only: Whether to run only fix-capable tools.
        check_only: Whether to run only check-oriented tools.

    Returns:
        LintSelectionParams: Structured selection configuration for lint.
    """

    return LintSelectionParams(
        filters=list(filters),
        only=list(only),
        language=list(language),
        fix_only=fix_only,
        check_only=check_only,
    )


def _runtime_concurrency_dependency(
    jobs: Annotated[
        int | None,
        typer.Option(None, "--jobs", "-j", min=1, help=JOBS_HELP),
    ],
    bail: Annotated[bool, typer.Option(False, "--bail", help="Exit on first tool failure.")],
    use_local_linters: Annotated[
        bool,
        typer.Option(False, "--use-local-linters", help=USE_LOCAL_LINTERS_HELP),
    ],
) -> RuntimeConcurrencyParams:
    """Return concurrency parameters controlling parallel execution.

    Args:
        jobs: Optional explicit job count provided by the user.
        bail: Flag indicating whether execution should abort on first failure.
        use_local_linters: Whether vendored linters should be preferred.

    Returns:
        RuntimeConcurrencyParams: Structured concurrency parameters.
    """

    return RuntimeConcurrencyParams(jobs=jobs, bail=bail, use_local_linters=use_local_linters)


def _runtime_cache_dependency(
    no_cache: Annotated[bool, typer.Option(False, help="Disable on-disk result caching.")],
    cache_dir: Annotated[
        Path,
        typer.Option(Path(".lint-cache"), "--cache-dir", help=CACHE_DIR_HELP),
    ],
) -> RuntimeCacheParams:
    """Return runtime cache parameters derived from CLI options.

    Args:
        no_cache: Flag indicating whether caching should be disabled.
        cache_dir: Directory used to persist cached results.

    Returns:
        RuntimeCacheParams: Structured cache settings for lint execution.
    """

    return RuntimeCacheParams(no_cache=no_cache, cache_dir=cache_dir)


def _execution_runtime_dependency(
    concurrency: Annotated[RuntimeConcurrencyParams, Depends(_runtime_concurrency_dependency)],
    cache: Annotated[RuntimeCacheParams, Depends(_runtime_cache_dependency)],
    strict_config: Annotated[
        bool,
        typer.Option(False, "--strict-config", help=STRICT_CONFIG_HELP),
    ],
) -> LintExecutionRuntimeParams:
    """Combine concurrency and cache settings into execution parameters.

    Args:
        concurrency: Structured concurrency parameters.
        cache: Cache configuration parameters.
        strict_config: Whether configuration warnings should become errors.

    Returns:
        LintExecutionRuntimeParams: Execution runtime configuration consumed by
        the lint command.
    """

    return LintExecutionRuntimeParams(
        jobs=concurrency.jobs,
        bail=concurrency.bail,
        no_cache=cache.no_cache,
        cache_dir=cache.cache_dir,
        use_local_linters=concurrency.use_local_linters,
        strict_config=strict_config,
    )


def _output_toggle_dependency(
    verbose: Annotated[bool, typer.Option(False, help="Verbose output.")],
    quiet: Annotated[bool, typer.Option(False, "--quiet", "-q", help="Minimal output.")],
    no_color: Annotated[bool, typer.Option(False, help="Disable ANSI colour output.")],
    no_emoji: Annotated[bool, typer.Option(False, help="Disable emoji output.")],
    debug: Annotated[bool, typer.Option(False, "--debug", help="Emit detailed execution diagnostics.")],
) -> LintOutputToggles:
    """Return the raw CLI toggles backing output behaviour."""

    return LintOutputToggles(
        verbose=verbose,
        quiet=quiet,
        no_color=no_color,
        no_emoji=no_emoji,
        debug=debug,
    )


def _output_params_dependency(
    toggles: Annotated[LintOutputToggles, Depends(_output_toggle_dependency)],
    output_mode: Annotated[
        str,
        typer.Option(OUTPUT_MODE_CONCISE, "--output", help=OUTPUT_MODE_HELP),
    ],
) -> LintOutputParams:
    """Return rendering parameters for console output.

    Args:
        toggles: Structured booleans describing output toggles.
        output_mode: Raw output mode supplied by the user.

    Returns:
        LintOutputParams: Structured rendering parameters.
    """

    return LintOutputParams(
        verbose=toggles.verbose,
        quiet=toggles.quiet,
        no_color=toggles.no_color,
        no_emoji=toggles.no_emoji,
        debug=toggles.debug,
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
    """Return reporting parameters determining diagnostic artifact output.

    Args:
        show_passing: Whether to include passing diagnostics in output.
        no_stats: Whether to suppress summary statistics.
        report_json: Optional JSON report destination.
        sarif_out: Optional SARIF output path.
        pr_summary_out: Optional PR summary output path.

    Returns:
        LintReportingParams: Structured reporting options.
    """

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
    """Return PR summary configuration derived from CLI flags.

    Args:
        pr_summary_limit: Maximum number of diagnostics in the summary.
        pr_summary_min_severity: Minimum severity to include in the summary.
        pr_summary_template: Template string used to format entries.
        advice: Whether SOLID advice should be included.

    Returns:
        LintSummaryParams: Structured summary configuration for lint.
    """

    return LintSummaryParams(
        pr_summary_limit=pr_summary_limit,
        pr_summary_min_severity=_coerce_pr_summary_severity(pr_summary_min_severity),
        pr_summary_template=pr_summary_template,
        advice=advice,
    )


def _override_formatting_dependency(
    line_length: Annotated[int, typer.Option(120, "--line-length", help=LINE_LENGTH_HELP)],
    sql_dialect: Annotated[str, typer.Option("postgresql", "--sql-dialect", help=SQL_DIALECT_HELP)],
    python_version: Annotated[
        str | None,
        typer.Option(None, "--python-version", help=PYTHON_VERSION_HELP),
    ],
) -> OverrideFormattingParams:
    """Return formatting overrides shared across compatible tools.

    Args:
        line_length: Global maximum line length.
        sql_dialect: Default SQL dialect for formatting tools.
        python_version: Optional Python version advertised to tools.

    Returns:
        OverrideFormattingParams: Structured formatting overrides.
    """

    normalized_python_version = python_version.strip() if python_version else None
    return OverrideFormattingParams(
        line_length=line_length,
        sql_dialect=sql_dialect,
        python_version=normalized_python_version,
    )


def _override_threshold_dependency(
    max_complexity: Annotated[
        int | None,
        typer.Option(None, "--max-complexity", min=1, help=MAX_COMPLEXITY_HELP),
    ],
    max_arguments: Annotated[
        int | None,
        typer.Option(None, "--max-arguments", min=1, help=MAX_ARGUMENTS_HELP),
    ],
) -> OverrideThresholdParams:
    """Return shared threshold overrides for complexity heuristics.

    Args:
        max_complexity: Upper bound for cyclomatic complexity.
        max_arguments: Upper bound for function arguments.

    Returns:
        OverrideThresholdParams: Structured complexity overrides.
    """

    return OverrideThresholdParams(
        max_complexity=max_complexity,
        max_arguments=max_arguments,
    )


def _override_strictness_dependency(
    type_checking: Annotated[
        str | None,
        typer.Option(None, "--type-checking", case_sensitive=False, help=TYPE_CHECKING_HELP),
    ],
) -> OverrideStrictnessParams:
    """Return strictness overrides for type-checking controls.

    Args:
        type_checking: Optional strictness value provided on the CLI.

    Returns:
        OverrideStrictnessParams: Structured strictness overrides.
    """

    return OverrideStrictnessParams(
        type_checking=_coerce_optional_strictness(type_checking),
    )


def _override_params_dependency(
    formatting: Annotated[OverrideFormattingParams, Depends(_override_formatting_dependency)],
    thresholds: Annotated[OverrideThresholdParams, Depends(_override_threshold_dependency)],
    strictness: Annotated[OverrideStrictnessParams, Depends(_override_strictness_dependency)],
) -> LintOverrideParams:
    """Combine override parameters into the shape expected by lint.

    Args:
        formatting: Formatting overrides including line length and dialect.
        thresholds: Complexity-related thresholds.
        strictness: Type-checking strictness overrides.

    Returns:
        LintOverrideParams: Structured override configuration for lint.
    """

    return LintOverrideParams(
        line_length=formatting.line_length,
        sql_dialect=formatting.sql_dialect,
        max_complexity=thresholds.max_complexity,
        max_arguments=thresholds.max_arguments,
        type_checking=strictness.type_checking,
        python_version=formatting.python_version,
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
    """Return severity overrides captured from CLI options.

    Args:
        bandit_severity: Optional Bandit severity override.
        bandit_confidence: Optional Bandit confidence override.
        pylint_fail_under: Optional pylint fail-under score.
        sensitivity: Optional global sensitivity override.

    Returns:
        LintSeverityParams: Structured severity overrides.
    """

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


def _meta_action_toggle_dependency(
    doctor: Annotated[
        bool,
        typer.Option(False, "--doctor", help="Run environment diagnostics and exit."),
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
    explain_tools: Annotated[
        bool,
        typer.Option(False, "--explain-tools", help=EXPLAIN_TOOLS_HELP),
    ],
) -> MetaActionToggleParams:
    """Return boolean toggles for meta actions."""

    return MetaActionToggleParams(
        doctor=doctor,
        fetch_all_tools=fetch_all_tools,
        validate_schema=validate_schema,
        normal=normal,
        explain_tools=explain_tools,
    )


def _meta_action_info_dependency(
    tool_info: Annotated[
        str | None,
        typer.Option(None, "--tool-info", metavar="TOOL", help=TOOL_INFO_HELP),
    ],
) -> MetaActionInfo:
    """Return optional informational CLI toggles."""

    return MetaActionInfo(tool_info=tool_info)


def _meta_action_dependency(
    toggles: Annotated[MetaActionToggleParams, Depends(_meta_action_toggle_dependency)],
    info: Annotated[MetaActionInfo, Depends(_meta_action_info_dependency)],
) -> MetaActionParams:
    """Return meta-action toggles captured from CLI options."""

    return MetaActionParams(
        doctor=toggles.doctor,
        tool_info=info.tool_info,
        fetch_all_tools=toggles.fetch_all_tools,
        validate_schema=toggles.validate_schema,
        normal=toggles.normal,
        explain_tools=toggles.explain_tools,
    )


def _meta_analysis_checks_dependency(
    check_docstrings: Annotated[
        bool,
        typer.Option(False, "--check-docstrings", help=DOCSTRINGS_HELP),
    ],
    check_suppressions: Annotated[
        bool,
        typer.Option(False, "--check-suppressions", help=SUPPRESSIONS_HELP),
    ],
    check_types_strict: Annotated[
        bool,
        typer.Option(False, "--check-types-strict", help=TYPING_HELP),
    ],
    check_missing: Annotated[
        bool,
        typer.Option(False, "--check-missing", help=MISSING_HELP),
    ],
) -> MetaAnalysisChecks:
    """Return analysis-focused meta-check toggles."""

    return MetaAnalysisChecks(
        check_docstrings=check_docstrings,
        check_suppressions=check_suppressions,
        check_types_strict=check_types_strict,
        check_missing=check_missing,
    )


def _runtime_core_checks_dependency(
    check_closures: Annotated[
        bool,
        typer.Option(False, "--check-closures", help=CLOSURES_HELP),
    ],
    check_signatures: Annotated[
        bool,
        typer.Option(False, "--check-signatures", help=SIGNATURES_HELP),
    ],
    check_cache_usage: Annotated[
        bool,
        typer.Option(False, "--check-cache-usage", help=CACHE_HELP),
    ],
    check_value_types: Annotated[
        bool,
        typer.Option(
            False, "--check-value-types", help="Verify pyqa value-type helpers expose ergonomic dunder methods."
        ),
    ],
    check_value_types_general: Annotated[
        bool,
        typer.Option(
            False,
            "--check-value-types-general",
            help=VALUE_TYPES_GENERAL_HELP,
        ),
    ],
) -> RuntimeCoreChecks:
    """Return the runtime core check toggles."""

    return RuntimeCoreChecks(
        check_closures=check_closures,
        check_signatures=check_signatures,
        check_cache_usage=check_cache_usage,
        check_value_types=check_value_types,
        check_value_types_general=check_value_types_general,
    )


def _runtime_interface_checks_dependency(
    check_interfaces: Annotated[
        bool,
        typer.Option(False, "--check-interfaces", help=CHECK_INTERFACES_HELP),
    ],
    check_di: Annotated[
        bool,
        typer.Option(False, "--check-di", help=CHECK_DI_HELP),
    ],
    check_module_docs: Annotated[
        bool,
        typer.Option(False, "--check-module-docs", help=CHECK_MODULE_DOCS_HELP),
    ],
    check_pyqa_python_hygiene: Annotated[
        bool,
        typer.Option(False, "--check-pyqa-python-hygiene", help=PYQA_PYTHON_HYGIENE_HELP),
    ],
) -> RuntimeInterfaceChecks:
    """Return interface-oriented runtime toggles."""

    return RuntimeInterfaceChecks(
        check_interfaces=check_interfaces,
        check_di=check_di,
        check_module_docs=check_module_docs,
        check_pyqa_python_hygiene=check_pyqa_python_hygiene,
    )


def _runtime_policy_checks_dependency(
    show_valid_suppressions: Annotated[
        bool,
        typer.Option(False, "--show-valid-suppressions", help=SHOW_VALID_SUPPRESSIONS_HELP),
    ],
    check_license_header: Annotated[
        bool,
        typer.Option(False, "--check-license-header", help=LICENSE_HEADER_HELP),
    ],
    check_copyright: Annotated[
        bool,
        typer.Option(False, "--check-copyright", help=COPYRIGHT_HELP),
    ],
    check_python_hygiene: Annotated[
        bool,
        typer.Option(False, "--check-python-hygiene", help=PYTHON_HYGIENE_HELP),
    ],
) -> RuntimePolicyChecks:
    """Return policy-oriented runtime toggles."""

    return RuntimePolicyChecks(
        show_valid_suppressions=show_valid_suppressions,
        check_license_header=check_license_header,
        check_copyright=check_copyright,
        check_python_hygiene=check_python_hygiene,
    )


def _runtime_additional_checks_dependency(
    check_file_size: Annotated[
        bool,
        typer.Option(False, "--check-file-size", help=FILE_SIZE_HELP),
    ],
    check_schema_sync: Annotated[
        bool,
        typer.Option(False, "--check-schema-sync", help=SCHEMA_SYNC_HELP),
    ],
    pyqa_rules: Annotated[
        bool,
        typer.Option(False, "--pyqa-rules", help=PYQA_RULES_HELP),
    ],
) -> RuntimeAdditionalChecks:
    """Return advanced runtime toggle selections."""

    return RuntimeAdditionalChecks(
        check_file_size=check_file_size,
        check_schema_sync=check_schema_sync,
        pyqa_rules=pyqa_rules,
    )


def _meta_runtime_checks_dependency(
    core: Annotated[RuntimeCoreChecks, Depends(_runtime_core_checks_dependency)],
    interface: Annotated[RuntimeInterfaceChecks, Depends(_runtime_interface_checks_dependency)],
    policy: Annotated[RuntimePolicyChecks, Depends(_runtime_policy_checks_dependency)],
    additional: Annotated[RuntimeAdditionalChecks, Depends(_runtime_additional_checks_dependency)],
) -> MetaRuntimeChecks:
    """Return runtime-focused meta-check toggles."""

    return MetaRuntimeChecks(
        check_closures=core.check_closures,
        check_signatures=core.check_signatures,
        check_cache_usage=core.check_cache_usage,
        check_value_types=core.check_value_types,
        check_value_types_general=core.check_value_types_general,
        check_interfaces=interface.check_interfaces,
        check_di=interface.check_di,
        check_module_docs=interface.check_module_docs,
        check_pyqa_python_hygiene=interface.check_pyqa_python_hygiene,
        show_valid_suppressions=policy.show_valid_suppressions,
        check_license_header=policy.check_license_header,
        check_copyright=policy.check_copyright,
        check_python_hygiene=policy.check_python_hygiene,
        check_file_size=additional.check_file_size,
        check_schema_sync=additional.check_schema_sync,
        pyqa_rules=additional.pyqa_rules,
    )


def _meta_params_dependency(
    actions: Annotated[MetaActionParams, Depends(_meta_action_dependency)],
    analysis_checks: Annotated[MetaAnalysisChecks, Depends(_meta_analysis_checks_dependency)],
    runtime_checks: Annotated[MetaRuntimeChecks, Depends(_meta_runtime_checks_dependency)],
) -> LintMetaParams:
    """Return meta-command parameters influencing lint execution flow."""

    if actions.normal:
        analysis = MetaAnalysisChecks(
            check_docstrings=True,
            check_suppressions=True,
            check_types_strict=True,
            check_missing=True,
        )
        runtime = MetaRuntimeChecks(
            check_closures=True,
            check_signatures=True,
            check_cache_usage=True,
            check_value_types=True,
            check_value_types_general=True,
            check_interfaces=True,
            check_di=True,
            check_module_docs=True,
            check_pyqa_python_hygiene=True,
            show_valid_suppressions=False,
            check_license_header=True,
            check_copyright=True,
            check_python_hygiene=True,
            check_file_size=True,
            check_schema_sync=True,
            pyqa_rules=True,
        )
    else:
        analysis = analysis_checks
        runtime = runtime_checks

    return LintMetaParams(actions=actions, analysis=analysis, runtime=runtime)


def _build_target_group(
    path_params: Annotated[LintPathParams, Depends(_path_params_dependency)],
    git_params: Annotated[LintGitParams, Depends(_git_params_dependency)],
) -> LintTargetGroup:
    """Return a target group combining filesystem and git parameters.

    Args:
        path_params: Structured filesystem path parameters.
        git_params: Structured git discovery parameters.

    Returns:
        LintTargetGroup: Aggregated target parameters for lint options.
    """

    return LintTargetGroup(path=path_params, git=git_params)


def _build_execution_group(
    selection: Annotated[LintSelectionParams, Depends(_selection_params_dependency)],
    runtime: Annotated[LintExecutionRuntimeParams, Depends(_execution_runtime_dependency)],
) -> LintExecutionGroup:
    """Return execution parameters combining selection and runtime input.

    Args:
        selection: Structured tool selection parameters.
        runtime: Structured runtime execution configuration.

    Returns:
        LintExecutionGroup: Aggregated execution parameters for lint options.
    """

    return LintExecutionGroup(selection=selection, runtime=runtime)


def _build_output_group(
    output_params: Annotated[LintOutputParams, Depends(_output_params_dependency)],
    reporting_params: Annotated[LintReportingParams, Depends(_reporting_params_dependency)],
    summary_params: Annotated[LintSummaryParams, Depends(_summary_params_dependency)],
) -> LintOutputGroup:
    """Return output parameters combining rendering, reporting, and summary.

    Args:
        output_params: Structured rendering configuration.
        reporting_params: Structured reporting configuration.
        summary_params: Structured summary configuration.

    Returns:
        LintOutputGroup: Aggregated output parameters for lint options.
    """

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
    """Return advanced configuration combining overrides, severity, and meta.

    Args:
        overrides: Structured override configuration.
        severity: Structured severity overrides.
        meta: Structured meta-action configuration.

    Returns:
        LintAdvancedGroup: Aggregated advanced parameters for lint options.
    """

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
    """Assemble structured CLI input dataclasses for lint execution.

    Args:
        targets: Aggregated target parameters.
        execution: Aggregated execution parameters.
        output: Aggregated output parameters.
        advanced: Aggregated advanced parameters.

    Returns:
        LintCLIInputs: Fully constructed CLI inputs consumed by lint services.
    """

    return LintCLIInputs(
        targets=targets,
        execution=execution,
        output=output,
        advanced=advanced,
    )


__all__ = (
    "ADVICE_HELP",
    "BANDIT_CONFIDENCE_HELP",
    "BANDIT_LEVEL_CHOICES",
    "BANDIT_SEVERITY_HELP",
    "CACHE_DIR_HELP",
    "DOCSTRINGS_HELP",
    "MISSING_HELP",
    "SUPPRESSIONS_HELP",
    "TYPING_HELP",
    "CLOSURES_HELP",
    "SIGNATURES_HELP",
    "CACHE_HELP",
    "CHECK_DI_HELP",
    "CHECK_INTERFACES_HELP",
    "CHECK_MODULE_DOCS_HELP",
    "COPYRIGHT_HELP",
    "FETCH_ALL_TOOLS_HELP",
    "FILTER_HELP",
    "FILE_SIZE_HELP",
    "JOBS_HELP",
    "LINE_LENGTH_HELP",
    "LintDisplayOptions",
    "LICENSE_HEADER_HELP",
    "NORMAL_PRESET_HELP",
    "OUTPUT_MODE_CHOICES",
    "OUTPUT_MODE_CONCISE",
    "OUTPUT_MODE_HELP",
    "PR_SUMMARY_MIN_SEVERITY_HELP",
    "PR_SUMMARY_OUT_HELP",
    "PR_SUMMARY_SEVERITIES",
    "PR_SUMMARY_TEMPLATE_HELP",
    "PYLINT_FAIL_UNDER_HELP",
    "PYTHON_HYGIENE_HELP",
    "PYQA_PYTHON_HYGIENE_HELP",
    "REPORT_JSON_HELP",
    "SENSITIVITY_CHOICES",
    "SENSITIVITY_HELP",
    "STRICTNESS_CHOICES",
    "STRICT_CONFIG_HELP",
    "SCHEMA_SYNC_HELP",
    "VALUE_TYPES_GENERAL_HELP",
    "SHOW_VALID_SUPPRESSIONS_HELP",
    "TOOL_INFO_HELP",
    "TYPE_CHECKING_HELP",
    "USE_LOCAL_LINTERS_HELP",
    "VALIDATE_SCHEMA_HELP",
    "_build_lint_cli_inputs",
)
