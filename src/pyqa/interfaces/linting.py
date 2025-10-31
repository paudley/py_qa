# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Protocols describing linting state shared across pyqa modules."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final, Literal, Protocol, TypeAlias, runtime_checkable

from rich.console import Console

from pyqa.interfaces.discovery import DiscoveryOptions

from .common import RepositoryRootProvider
from .tools import (
    BanditLevelLiteral,
)
from .tools import ExecutionOptions as ToolExecutionOptions
from .tools import RuntimeOptions as ToolRuntimeOptions
from .tools import (
    SensitivityLiteral,
    StrictnessLiteral,
)

LintOptionValue: TypeAlias = bool | int | float | str | Path | None | Sequence[str] | Sequence[Path]
OutputModeLiteral: TypeAlias = Literal["concise", "pretty", "raw"]
PRSummarySeverityLiteral: TypeAlias = Literal["error", "warning", "notice", "note"]


@runtime_checkable
class CLILogger(Protocol):
    """Protocol describing logging helpers supplied by the CLI layer."""

    __slots__ = ()

    def fail(self, message: str) -> None:
        """Render a failure ``message`` honouring CLI presentation preferences.

        Args:
            message: Message string describing the failure condition.
        """

        raise NotImplementedError("CLILogger.fail must be implemented")

    def warn(self, message: str) -> None:
        """Render a warning ``message`` honouring CLI presentation preferences.

        Args:
            message: Message string describing the warning condition.
        """

        raise NotImplementedError("CLILogger.warn must be implemented")

    def ok(self, message: str) -> None:
        """Render a success ``message`` honouring CLI presentation preferences.

        Args:
            message: Message string describing the success condition.
        """

        raise NotImplementedError("CLILogger.ok must be implemented")

    def echo(self, message: str) -> None:
        """Write ``message`` to stdout using the CLI output mechanism.

        Args:
            message: Message string sent to standard output.
        """

        raise NotImplementedError("CLILogger.echo must be implemented")

    def debug(self, message: str) -> None:
        """Emit a debug ``message`` when debug logging is enabled.

        Args:
            message: Message string describing the debug condition.
        """

        raise NotImplementedError("CLILogger.debug must be implemented")

    @property
    def console(self) -> Console:
        """Return the Rich console used for rendering CLI output.

        Returns:
            Console: Rich console instance bound to the logger.
        """

        raise NotImplementedError("CLILogger.console must be implemented")


@runtime_checkable
class CLIDisplayOptions(Protocol):
    """Protocol describing CLI display toggles shared with linters."""

    __slots__ = ()

    @property
    def no_emoji(self) -> bool:
        """Return ``True`` when emoji output is disabled.

        Returns:
            bool: ``True`` when emoji output is disabled.
        """

        raise NotImplementedError("CLIDisplayOptions.no_emoji must be implemented")

    @property
    def quiet(self) -> bool:
        """Return ``True`` when quiet output is enabled.

        Returns:
            bool: ``True`` when quiet output is enabled.
        """

        raise NotImplementedError("CLIDisplayOptions.quiet must be implemented")

    @property
    def verbose(self) -> bool:
        """Return ``True`` when verbose output is enabled.

        Returns:
            bool: ``True`` when verbose output is enabled.
        """

        raise NotImplementedError("CLIDisplayOptions.verbose must be implemented")

    @property
    def debug(self) -> bool:
        """Return ``True`` when debug output is enabled.

        Returns:
            bool: ``True`` when debug output is enabled.
        """

        raise NotImplementedError("CLIDisplayOptions.debug must be implemented")

    @property
    def no_color(self) -> bool:
        """Return ``True`` when colour output is disabled.

        Returns:
            bool: ``True`` when colour output is disabled.
        """

        raise NotImplementedError("CLIDisplayOptions.no_color must be implemented")

    @property
    def output_mode(self) -> OutputModeLiteral:
        """Return the configured output mode literal.

        Returns:
            OutputModeLiteral: Output mode literal requested by the user.
        """

        raise NotImplementedError("CLIDisplayOptions.output_mode must be implemented")

    @property
    def advice(self) -> bool:
        """Return ``True`` when advisory output is enabled.

        Returns:
            bool: ``True`` when advisory output is enabled.
        """

        raise NotImplementedError("CLIDisplayOptions.advice must be implemented")

    def to_flags(self) -> tuple[bool, bool, bool, bool, bool, OutputModeLiteral, bool]:
        """Return the toggles in a deterministic tuple representation.

        Returns:
            tuple[bool, bool, bool, bool, bool, OutputModeLiteral, bool]:
            Tuple of (no_emoji, quiet, verbose, debug, no_color, output_mode, advice).
        """

        return (
            self.no_emoji,
            self.quiet,
            self.verbose,
            self.debug,
            self.no_color,
            self.output_mode,
            self.advice,
        )


@runtime_checkable
class MetaActionParamsView(Protocol):
    """Protocol describing meta action toggles supplied by the CLI.

    Attributes:
        doctor: ``True`` when diagnostics should run and exit immediately.
        tool_info: Optional tool name requested for metadata output.
        fetch_all_tools: ``True`` when tool downloads should be triggered.
        validate_schema: ``True`` when schema validation is requested.
        normal: ``True`` when the normal preset should be applied.
        explain_tools: ``True`` when tool explanations should be rendered.
    """

    __slots__ = ()

    tool_info: str | None
    doctor: bool
    normal: bool
    fetch_all_tools: bool
    validate_schema: bool
    explain_tools: bool


@runtime_checkable
class MetaAnalysisChecksView(Protocol):
    """Protocol describing analysis-oriented meta toggles.

    Attributes:
        check_docstrings: ``True`` when docstring validation is enabled.
        check_suppressions: ``True`` when suppression validation is enabled.
        check_types_strict: ``True`` when strict type checking is enabled.
        check_missing: ``True`` when missing dependency checks are enabled.
    """

    __slots__ = ()

    check_types_strict: bool
    check_docstrings: bool
    check_missing: bool
    check_suppressions: bool


@runtime_checkable
class RuntimeCoreChecksView(Protocol):
    """Protocol describing runtime core lint toggles.

    Attributes:
        check_closures: ``True`` when closure validation is enabled.
        check_conditional_imports: ``True`` when conditional import checks are enabled.
        check_signatures: ``True`` when signature validation is enabled.
        check_cache_usage: ``True`` when cache usage validation is enabled.
        check_value_types: ``True`` when value-type validation is enabled.
        check_value_types_general: ``True`` when general value-type validation is enabled.
    """

    __slots__ = ()

    check_conditional_imports: bool
    check_cache_usage: bool
    check_closures: bool
    check_signatures: bool
    check_value_types_general: bool
    check_value_types: bool


@runtime_checkable
class RuntimeInterfaceChecksView(Protocol):
    """Protocol describing runtime interface lint toggles.

    Attributes:
        check_interfaces: ``True`` when interface checks are enabled.
        check_di: ``True`` when dependency-injection checks are enabled.
        check_module_docs: ``True`` when module documentation checks are enabled.
        check_pyqa_python_hygiene: ``True`` when pyqa-specific hygiene checks are enabled.
    """

    __slots__ = ()

    check_module_docs: bool
    check_interfaces: bool
    check_pyqa_python_hygiene: bool
    check_di: bool


@runtime_checkable
class RuntimePolicyChecksView(Protocol):
    """Protocol describing runtime policy lint toggles.

    Attributes:
        show_valid_suppressions: ``True`` when valid suppression reporting is enabled.
        check_license_header: ``True`` when license header validation is enabled.
        check_copyright: ``True`` when copyright validation is enabled.
        check_python_hygiene: ``True`` when Python hygiene validation is enabled.
    """

    __slots__ = ()

    check_python_hygiene: bool
    show_valid_suppressions: bool
    check_license_header: bool
    check_copyright: bool


@runtime_checkable
class RuntimeAdditionalChecksView(Protocol):
    """Protocol describing additional runtime lint toggles.

    Attributes:
        check_file_size: ``True`` when file size checks are enabled.
        check_schema_sync: ``True`` when schema sync checks are enabled.
        pyqa_rules: ``True`` when pyqa rules checks are enabled.
    """

    __slots__ = ()

    pyqa_rules: bool
    check_schema_sync: bool
    check_file_size: bool


@runtime_checkable
class MetaRuntimeChecksView(Protocol):
    """Protocol describing grouped runtime lint toggles.

    Attributes:
        core: Runtime core lint toggles.
        interface: Runtime interface lint toggles.
        policy: Runtime policy lint toggles.
        additional: Runtime additional lint toggles.
    """

    __slots__ = ()

    policy: RuntimePolicyChecksView
    core: RuntimeCoreChecksView
    additional: RuntimeAdditionalChecksView
    interface: RuntimeInterfaceChecksView


@runtime_checkable
class LintMetaParams(Protocol):
    """Protocol describing lint meta parameter bundles."""

    __slots__ = ()

    @property
    def actions(self) -> MetaActionParamsView:
        """Return meta action toggles."""

        raise NotImplementedError("LintMetaParams.actions must be implemented")

    @property
    def analysis(self) -> MetaAnalysisChecksView:
        """Return meta analysis toggles."""

        raise NotImplementedError("LintMetaParams.analysis must be implemented")

    @property
    def runtime(self) -> MetaRuntimeChecksView:
        """Return grouped runtime toggles."""

        raise NotImplementedError("LintMetaParams.runtime must be implemented")

    def __getattr__(self, attribute: str) -> bool | str | None:
        """Return the value of an attribute proxied through meta parameters.

        Args:
            attribute: Attribute name expected to resolve through meta toggles.

        Returns:
            bool | str | None: Resolved attribute value.
        """

        raise NotImplementedError("LintMetaParams.__getattr__ must be implemented")


@runtime_checkable
class LintOutputArtifacts(Protocol):
    """Protocol describing filesystem artefacts produced by lint operations."""

    __slots__ = ()

    @property
    def report_json(self) -> Path | None:
        """Return the optional path storing JSON report output."""

        raise NotImplementedError("LintOutputArtifacts.report_json must be implemented")

    @property
    def sarif_out(self) -> Path | None:
        """Return the optional path storing SARIF output."""

        raise NotImplementedError("LintOutputArtifacts.sarif_out must be implemented")

    @property
    def pr_summary_out(self) -> Path | None:
        """Return the optional path storing PR summary output."""

        raise NotImplementedError("LintOutputArtifacts.pr_summary_out must be implemented")

    def as_tuple(self) -> tuple[Path | None, Path | None, Path | None]:
        """Return the artefact paths as a tuple ordered by creation priority.

        Returns:
            tuple[Path | None, Path | None, Path | None]: Tuple of artefact paths.
        """

        return (self.report_json, self.sarif_out, self.pr_summary_out)


@runtime_checkable
class LintGitOptionsView(Protocol):
    """Protocol describing git discovery overrides supplied via the CLI.

    Attributes:
        changed_only: ``True`` when only changed files should be linted.
        diff_ref: Diff reference used when selecting changed files.
        include_untracked: ``True`` when untracked files should be included.
        base_branch: Optional base branch used for diff calculations.
        no_lint_tests: ``True`` when test files should be excluded.
    """

    __slots__ = ()

    include_untracked: bool
    diff_ref: str
    base_branch: str | None
    changed_only: bool
    no_lint_tests: bool


@runtime_checkable
class LintSelectionOptionsView(Protocol):
    """Protocol describing tool selection overrides supplied via the CLI.

    Attributes:
        filters: Tool filter expressions applied to the lint run.
        only: Explicit tool names requested by the user.
        language: Language filters applied to the lint run.
        fix_only: ``True`` when only fix-capable tools should be executed.
        check_only: ``True`` when only check-capable tools should be executed.
    """

    __slots__ = ()

    language: Sequence[str]
    filters: Sequence[str]
    check_only: bool
    only: Sequence[str]
    fix_only: bool


@runtime_checkable
class LintSummaryOptionsView(Protocol):
    """Protocol describing summary rendering preferences.

    Attributes:
        show_passing: ``True`` when passing diagnostics should be displayed.
        no_stats: ``True`` when summary statistics should be suppressed.
        pr_summary_out: Optional path for PR summary output.
        pr_summary_limit: Maximum number of findings included in summaries.
        pr_summary_min_severity: Minimum severity level included in summaries.
        pr_summary_template: Template used for PR summary generation.
    """

    __slots__ = ()

    pr_summary_template: str
    pr_summary_out: Path | None
    pr_summary_min_severity: PRSummarySeverityLiteral
    show_passing: bool
    pr_summary_limit: int
    no_stats: bool


@runtime_checkable
class LintOutputBundleView(Protocol):
    """Protocol describing the composed output configuration bundle.

    Attributes:
        display: CLI display toggles applied to the lint run.
        summary: Summary rendering preferences applied to the lint run.
    """

    __slots__ = ()

    summary: LintSummaryOptionsView
    display: CLIDisplayOptions


@runtime_checkable
class LintComplexityOptionsView(Protocol):
    """Protocol describing complexity override options.

    Attributes:
        max_complexity: Optional maximum cyclomatic complexity.
        max_arguments: Optional maximum argument count.
    """

    __slots__ = ()

    max_arguments: int | None
    max_complexity: int | None


@runtime_checkable
class LintStrictnessOptionsView(Protocol):
    """Protocol describing strictness override options.

    Attributes:
        type_checking: Optional type checking strictness override.
    """

    __slots__ = ()

    type_checking: StrictnessLiteral | None


@runtime_checkable
class LintSeverityOptionsView(Protocol):
    """Protocol describing severity override options.

    Attributes:
        bandit_severity: Optional Bandit severity override.
        bandit_confidence: Optional Bandit confidence override.
        pylint_fail_under: Optional pylint score threshold.
        sensitivity: Optional pyqa sensitivity override.
    """

    __slots__ = ()

    sensitivity: SensitivityLiteral | None
    bandit_confidence: BanditLevelLiteral | None
    pylint_fail_under: float | None
    bandit_severity: BanditLevelLiteral | None


@runtime_checkable
class LintOverrideOptionsView(Protocol):
    """Protocol describing grouped override options for downstream tooling.

    Attributes:
        complexity: Complexity overrides applied to downstream tooling.
        strictness: Strictness overrides applied to downstream tooling.
        severity: Severity overrides applied to downstream tooling.
    """

    __slots__ = ()

    strictness: LintStrictnessOptionsView
    severity: LintSeverityOptionsView
    complexity: LintComplexityOptionsView


@runtime_checkable
class LintOptions(Protocol):
    """Protocol describing lint option payloads supplied by the CLI layer."""

    __slots__ = ()

    @property
    def target_options(self) -> LintTargetOptions:
        """Return target discovery options for the lint run."""

        raise NotImplementedError("LintOptions.target_options must be implemented")

    @property
    def git_options(self) -> LintGitOptionsView:
        """Return git discovery options configured for the lint run."""

        raise NotImplementedError("LintOptions.git_options must be implemented")

    @property
    def selection_options(self) -> LintSelectionOptionsView:
        """Return tool selection options configured for the lint run."""

        raise NotImplementedError("LintOptions.selection_options must be implemented")

    @property
    def output_bundle(self) -> LintOutputBundleView:
        """Return the output bundle governing reporting preferences."""

        raise NotImplementedError("LintOptions.output_bundle must be implemented")

    @property
    def execution_options(self) -> LintExecutionOptions:
        """Return execution options for downstream tools."""

        raise NotImplementedError("LintOptions.execution_options must be implemented")

    @property
    def override_options(self) -> LintOverrideOptionsView:
        """Return overrides applied to downstream tooling."""

        raise NotImplementedError("LintOptions.override_options must be implemented")

    @property
    def provided(self) -> frozenset[str]:
        """Return the set of CLI flags explicitly provided by the user."""

        raise NotImplementedError("LintOptions.provided must be implemented")

    def __getattr__(self, name: str) -> LintOptionValue:
        """Return nested option values resolved by attribute name.

        Args:
            name: Attribute name to resolve within composed option bundles.

        Returns:
            LintOptionValue: Resolved option value.
        """

        raise NotImplementedError("LintOptions.__getattr__ must be implemented")

    def __contains__(self, item: str) -> bool:
        """Return ``True`` when ``item`` was explicitly provided via the CLI."""

        raise NotImplementedError("LintOptions.__contains__ must be implemented")

    def __dir__(self) -> list[str]:
        """Return the attribute names available on the composed options."""

        raise NotImplementedError("LintOptions.__dir__ must be implemented")

    def with_added_provided(self, *flags: str) -> None:
        """Record additional CLI flags as explicitly provided."""

        raise NotImplementedError("LintOptions.with_added_provided must be implemented")

    def __repr__(self) -> str:
        """Return a deterministic representation helpful for debugging."""

        raise NotImplementedError("LintOptions.__repr__ must be implemented")


class SuppressionDirective(Protocol):
    """Protocol describing the metadata stored for an inline suppression directive."""

    @property
    def line(self) -> int:
        """Return the 1-based line number where the suppression appears.

        Returns:
            int: Line number associated with the suppression directive.
        """

        raise NotImplementedError

    @property
    def lints(self) -> Sequence[str]:
        """Return lint identifiers targeted by the suppression directive.

        Returns:
            Sequence[str]: Lint identifiers referenced by the directive.
        """

        raise NotImplementedError

    def lint_count(self) -> int:
        """Return the number of lint identifiers referenced by the directive.

        Returns:
            int: Count of lint identifiers captured by the directive.
        """

        return len(self.lints)


@runtime_checkable
class MissingFinding(Protocol):
    """Describe immutable attributes recorded for missing-code findings.

    Attributes:
        file: Path to the source file containing the finding.
        line: 1-based line number where the finding occurs.
        message: Human-readable description of the missing functionality.
        code: Diagnostic code associated with the missing finding.
    """

    @property
    def file(self) -> Path:
        """Return the source file containing the missing-code finding.

        Returns:
            Path: Source file path associated with the finding.
        """

        raise NotImplementedError

    @property
    def line(self) -> int:
        """Return the 1-based line number where the finding occurs.

        Returns:
            int: One-based line number for the finding.
        """

        raise NotImplementedError

    @property
    def message(self) -> str:
        """Return the human-readable description of the missing functionality.

        Returns:
            str: Human-readable diagnostic message.
        """

        raise NotImplementedError

    @property
    def code(self) -> str:
        """Return the diagnostic code associated with the missing finding.

        Returns:
            str: Diagnostic code describing the missing implementation.
        """

        raise NotImplementedError

    def location(self) -> tuple[Path, int]:
        """Return a tuple describing the file and line for the finding.

        Returns:
            tuple[Path, int]: Pair of (file path, 1-based line number).
        """

        return self.file, self.line


class SuppressionRegistry(Protocol):
    """Protocol describing suppression lookups required by internal linters."""

    def entries_for(self, path: Path) -> Sequence[SuppressionDirective]:
        """Return cached suppression directives for ``path``.

        Args:
            path: File whose suppressions should be loaded.

        Returns:
            Sequence[SuppressionDirective]: Cached suppression directives for ``path``.
        """

        raise NotImplementedError

    def should_suppress(self, path: Path, line: int, *, tool: str, code: str) -> bool:
        """Return ``True`` when the specified diagnostic should be suppressed.

        Args:
            path: File containing the diagnostic.
            line: 1-based line number of the diagnostic.
            tool: Tool identifier associated with the diagnostic.
            code: Diagnostic code emitted by the tool.

        Returns:
            bool: ``True`` when the diagnostic should be suppressed.
        """

        raise NotImplementedError


@runtime_checkable
class LintTargetOptions(DiscoveryOptions, Protocol):
    """Lint-specific wrapper around discovery options."""

    __slots__ = ()


@runtime_checkable
class LintRuntimeOptions(ToolRuntimeOptions, Protocol):
    """Execution runtime switches relevant to internal linters.

    Attributes:
        strict_config: Flag indicating whether strict configuration validation is enabled.
    """

    def is_strict_mode(self) -> bool:
        """Return ``True`` when strict configuration validation is active.

        Returns:
            bool: ``True`` when strict configuration validation is enabled.
        """

        return self.strict_config


@runtime_checkable
class LintExecutionOptions(ToolExecutionOptions, Protocol):
    """Execution option bundle made available to internal linters.

    Attributes:
        runtime: Runtime configuration derived from CLI inputs.
        formatting: Formatting overrides propagated to tooling.
    """

    def has_formatting_overrides(self) -> bool:
        """Return ``True`` when formatting overrides are present.

        Returns:
            bool: ``True`` if any formatting override fields are populated.
        """

        fmt = self.formatting
        return any(getattr(fmt, attr, None) for attr in ("line_length", "sql_dialect", "python_version"))


@runtime_checkable
class LintOptionsView(Protocol):
    """Composite lint options envelope exposed to internal linters.

    Attributes:
        target_options: Target discovery options for the active invocation.
        execution_options: Execution configuration for the active invocation.
    """

    @property
    def target_options(self) -> LintTargetOptions:
        """Return target discovery options for the active invocation.

        Returns:
            LintTargetOptions: Discovery options for the current run.
        """

        raise NotImplementedError

    @property
    def execution_options(self) -> LintExecutionOptions:
        """Return execution configuration for the active invocation.

        Returns:
            LintExecutionOptions: Execution configuration prepared for the run.
        """

        raise NotImplementedError

    def as_tuple(self) -> tuple[LintTargetOptions, LintExecutionOptions]:
        """Return the combined target and execution options.

        Returns:
            tuple[LintTargetOptions, LintExecutionOptions]: Paired view of options.
        """

        return (self.target_options, self.execution_options)


@runtime_checkable
class LintStateOptions(Protocol):
    """Expose option-level state shared with lint execution helpers."""

    @property
    def options(self) -> LintOptions | LintOptionsView:
        """Return the lint option bundle prepared by the CLI layer.

        Returns:
            LintOptions | LintOptionsView: Prepared lint option bundle.
        """

        raise NotImplementedError

    @property
    def meta(self) -> LintMetaParams:
        """Return meta flags controlling optional lint behaviours.

        Returns:
            LintMetaParams: Meta flags describing optional lint behaviours.
        """

        raise NotImplementedError

    def has_meta_flag(self, flag: str) -> bool:
        """Return ``True`` when ``flag`` is present on the meta options.

        Args:
            flag: Name of the meta attribute to query.

        Returns:
            bool: ``True`` when the corresponding meta attribute evaluates truthy.
        """

        return bool(getattr(self.meta, flag, False))


@runtime_checkable
class LintRunArtifacts(Protocol):
    """Expose artifact-level state shared across lint reporting helpers.

    Attributes:
        ignored_py_qa: Paths skipped due to ``PY_QA`` sentinel directories.
        artifacts: Filesystem artefacts requested for the lint run.
        display: Display options governing console output.
        logger: Logger instance bound to the lint run.
        suppressions: Optional suppression registry when configured.
    """

    ignored_py_qa: Sequence[str]
    artifacts: LintOutputArtifacts
    display: CLIDisplayOptions
    logger: CLILogger
    suppressions: SuppressionRegistry | None

    def iter_ignored_py_qa(self) -> Sequence[str]:
        """Return a tuple view of ``PY_QA`` entries skipped by the run.

        Returns:
            Sequence[str]: Tuple containing ignored ``PY_QA`` directory paths.
        """

        return tuple(self.ignored_py_qa)

    def has_suppressions(self) -> bool:
        """Return ``True`` when a suppression registry has been configured.

        Returns:
            bool: ``True`` if a suppression registry instance is present.
        """

        return self.suppressions is not None


@runtime_checkable
class PreparedLintState(RepositoryRootProvider, LintStateOptions, LintRunArtifacts, Protocol):
    """Minimal protocol describing the lint command state shared with linters."""

    __slots__ = ()


__all__: Final[list[str]] = [
    "CLIDisplayOptions",
    "CLILogger",
    "LintComplexityOptionsView",
    "LintExecutionOptions",
    "LintGitOptionsView",
    "LintMetaParams",
    "LintOptions",
    "LintOptionsView",
    "LintOutputArtifacts",
    "LintOutputBundleView",
    "LintOverrideOptionsView",
    "LintRuntimeOptions",
    "LintTargetOptions",
    "LintSelectionOptionsView",
    "LintRunArtifacts",
    "LintStateOptions",
    "LintSummaryOptionsView",
    "MissingFinding",
    "MetaActionParamsView",
    "MetaAnalysisChecksView",
    "MetaRuntimeChecksView",
    "PreparedLintState",
    "RuntimeAdditionalChecksView",
    "RuntimeCoreChecksView",
    "RuntimeInterfaceChecksView",
    "RuntimePolicyChecksView",
    "LintSeverityOptionsView",
    "LintStrictnessOptionsView",
    "SuppressionDirective",
    "SuppressionRegistry",
]
