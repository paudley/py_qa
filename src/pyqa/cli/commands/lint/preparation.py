# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Services for preparing lint command state from CLI inputs."""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import typer

from pyqa.core.config.constants import PYQA_LINT_DIR_NAME
from pyqa.interfaces.linting import CLILogger as CLILoggerView
from pyqa.linting.suppressions import SuppressionRegistry
from pyqa.platform.workspace import is_pyqa_lint_workspace

from ....config import default_parallel_jobs
from ....filesystem.paths import normalize_path
from ...core.options import (
    ExecutionFormattingOptions,
    ExecutionRuntimeOptions,
    LintComplexityOptions,
)
from ...core.options import LintDisplayOptions as OptionsDisplayOptions
from ...core.options import (
    LintExecutionOptions,
    LintGitOptions,
    LintOptionBundles,
    LintOptions,
    LintOutputBundle,
    LintOverrideOptions,
    LintSelectionOptions,
    LintSeverityOptions,
    LintStrictnessOptions,
    LintSummaryOptions,
    LintTargetOptions,
)
from ...core.utils import filter_pyqa_lint_paths
from .cli_models import LintDisplayOptions as CLIDisplayOptions
from .literals import OUTPUT_MODE_CONCISE
from .params import (
    RUNTIME_ADDITIONAL_FLAGS,
    RUNTIME_CORE_FLAGS,
    RUNTIME_INTERFACE_FLAGS,
    RUNTIME_POLICY_FLAGS,
    LintAdvancedGroup,
    LintCLIInputs,
    LintExecutionGroup,
    LintExecutionRuntimeParams,
    LintGitParams,
    LintMetaParams,
    LintOutputArtifacts,
    LintOutputGroup,
    LintOutputParams,
    LintOverrideParams,
    LintPathParams,
    LintReportingParams,
    LintSelectionParams,
    OutputModeLiteral,
)

PROVIDED_FLAG_OUTPUT_MODE: Final[str] = "output_mode"
PROVIDED_FLAG_ADVICE: Final[str] = "advice"
PROVIDED_FLAG_EXCLUDE: Final[str] = "exclude"
PROVIDED_FLAG_USE_LOCAL_LINTERS: Final[str] = "use_local_linters"
PROVIDED_FLAG_NO_LINT_TESTS: Final[str] = "no_lint_tests"
PROVIDED_FLAG_INTERNAL_LINTERS: Final[str] = "internal_linters"


@dataclass(slots=True)
class PreparedLintStateParams:
    """Grouped constructor parameters for :class:`PreparedLintState`."""

    options: LintOptions
    meta: LintMetaParams
    root: Path
    ignored_pyqa_lint: Sequence[str]
    artifacts: LintOutputArtifacts
    suppressions: SuppressionRegistry | None
    presentation: tuple[CLIDisplayOptions, CLILoggerView]


@dataclass(slots=True, init=False)
class PreparedLintState:
    """Contain normalized inputs and metadata required to execute linting."""

    options: LintOptions
    meta: LintMetaParams
    root: Path
    ignored_pyqa_lint: tuple[str, ...]
    artifacts: LintOutputArtifacts
    suppressions: SuppressionRegistry | None
    _presentation: tuple[CLIDisplayOptions, CLILoggerView]

    def __init__(self, params: PreparedLintStateParams) -> None:
        """Initialize the prepared lint state container.

        Args:
            params: Aggregated constructor parameters produced by the preparation services.
        """

        self.options = params.options
        self.meta = params.meta
        self.root = params.root
        self.ignored_pyqa_lint = tuple(params.ignored_pyqa_lint)
        self.artifacts = params.artifacts
        self.suppressions = params.suppressions
        self._presentation = params.presentation

    def has_meta_flag(self, flag: str) -> bool:
        """Return ``True`` when ``flag`` is present on the meta options.

        Args:
            flag: Name of the meta attribute to inspect.

        Returns:
            bool: ``True`` when the requested meta attribute evaluates to truthy.
        """

        return bool(getattr(self.meta, flag, False))

    def iter_ignored_pyqa_lint(self) -> tuple[str, ...]:
        """Return immutable view of ``PY_QA`` discovery exclusions.

        Returns:
            tuple[str, ...]: Tuple containing ignored ``PY_QA`` directories.
        """

        return self.ignored_pyqa_lint

    def has_suppressions(self) -> bool:
        """Return ``True`` when a suppression registry has been configured.

        Returns:
            bool: ``True`` when a suppression registry is available.
        """

        return self.suppressions is not None

    @property
    def display(self) -> CLIDisplayOptions:
        """Return display options governing console output.

        Returns:
            CLIDisplayOptions: Display configuration for lint output.
        """

        return self._presentation[0]

    @property
    def logger(self) -> CLILoggerView:
        """Return the logger instance bound to the lint run.

        Returns:
            CLILoggerView: Logger instance recording lint messages.
        """

        return self._presentation[1]


@dataclass(slots=True)
class NormalizedTargets:
    """Hold normalized path parameters and derived root information."""

    root: Path
    paths: list[Path]
    dirs: list[Path]
    exclude: list[Path]
    ignored_pyqa_lint: list[str]


@dataclass(slots=True)
class NormalPresetResult:
    """Store preset adjustments applied to options and flags."""

    output_mode: OutputModeLiteral
    advice: bool
    no_lint_tests: bool
    use_local_linters: bool
    exclude_paths: list[Path]
    provided_flags: set[str]


@dataclass(slots=True)
class NormalPresetState:
    """Encapsulate mutable preset fields prior to adjustments."""

    output_mode: OutputModeLiteral
    advice: bool
    no_lint_tests: bool
    use_local_linters: bool
    exclude_paths: list[Path]
    provided_flags: set[str]


@dataclass(slots=True)
class _LintOptionBuildContext:
    """Aggregate inputs required to construct ``LintOptions``."""

    inputs: LintCLIInputs
    normalized_targets: NormalizedTargets
    preset: NormalPresetResult
    display: CLIDisplayOptions
    artifacts: LintOutputArtifacts
    cache_dir: Path
    effective_jobs: int


def _build_lint_options(
    context: _LintOptionBuildContext,
) -> LintOptions:
    """Materialise ``LintOptions`` from normalized CLI inputs.

    Args:
        context: Aggregated parameters required to build lint options.

    Returns:
        LintOptions: Fully populated options dataclass ready for config building.
    """

    targets = context.inputs.targets
    execution = context.inputs.execution
    output = context.inputs.output
    advanced = context.inputs.advanced

    bundles = LintOptionBundles(
        targets=_build_target_options(context.normalized_targets, targets.path, context.preset),
        git=_build_git_options(targets.git, context.preset.no_lint_tests),
        selection=_build_selection_options(execution.selection),
        output=_build_output_bundle(output, context.display, context.artifacts, context.preset),
        execution=_build_execution_options(
            execution,
            advanced,
            context.cache_dir,
            context.preset.use_local_linters,
            context.effective_jobs,
        ),
        overrides=_build_override_options(advanced),
    )
    return LintOptions(bundles=bundles, provided=context.preset.provided_flags)


def prepare_lint_state(
    ctx: typer.Context,
    inputs: LintCLIInputs,
    *,
    logger: CLILoggerView,
) -> PreparedLintState:
    """Normalise CLI inputs and construct the options dataclass.

    Args:
        ctx: Typer context providing parameter source information.
        inputs: Structured CLI inputs derived from dependency injection.
        logger: CLI logger used to emit warnings during preparation.

    Returns:
        PreparedLintState: Aggregated state required to execute linting.
    """

    invocation_cwd = Path.cwd()
    normalized_targets = _normalize_targets(
        ctx,
        inputs.targets.path,
        invocation_cwd=invocation_cwd,
        logger=logger,
    )
    artifacts = _resolve_artifacts(inputs.output.reporting, invocation_cwd=invocation_cwd)
    display = _build_display_options(inputs.output.rendering)
    cache_dir = normalize_path(inputs.execution.runtime.cache_dir, base_dir=invocation_cwd)
    effective_jobs = _effective_jobs(inputs.execution.runtime)

    _validate_pylint_fail_under(inputs.advanced.severity.pylint_fail_under)

    provided = _collect_provided_flags(
        ctx,
        paths_provided=bool(normalized_targets.paths),
        exclusion_paths=normalized_targets.exclude,
        selection=inputs.execution.selection,
        directories=normalized_targets.dirs,
    )

    preset_state = NormalPresetState(
        output_mode=inputs.output.rendering.output_mode,
        advice=inputs.output.summary.advice,
        no_lint_tests=inputs.targets.git.no_lint_tests,
        use_local_linters=inputs.execution.runtime.use_local_linters,
        exclude_paths=normalized_targets.exclude,
        provided_flags=provided,
    )
    preset = _apply_normal_preset(meta=inputs.advanced.meta, state=preset_state)

    options = _build_lint_options(
        context=_LintOptionBuildContext(
            inputs=inputs,
            normalized_targets=normalized_targets,
            preset=preset,
            display=display,
            artifacts=artifacts,
            cache_dir=cache_dir,
            effective_jobs=effective_jobs,
        ),
    )
    params = PreparedLintStateParams(
        options=options,
        meta=inputs.advanced.meta,
        root=normalized_targets.root,
        ignored_pyqa_lint=tuple(normalized_targets.ignored_pyqa_lint),
        artifacts=artifacts,
        suppressions=SuppressionRegistry(normalized_targets.root),
        presentation=(display, logger),
    )
    return PreparedLintState(params)


# Internal helpers --------------------------------------------------------------------


def _build_target_options(
    normalized_targets: NormalizedTargets,
    target_params: LintPathParams,
    preset: NormalPresetResult,
) -> LintTargetOptions:
    """Return the :class:`LintTargetOptions` segment derived from CLI inputs.

    Args:
        normalized_targets: Canonicalised target paths and directories.
        target_params: Raw target parameters derived from CLI arguments.
        preset: Effective preset adjustments applied during option collection.

    Returns:
        LintTargetOptions: Options describing filesystem discovery inputs.
    """

    return LintTargetOptions(
        root=normalized_targets.root,
        paths=list(normalized_targets.paths),
        dirs=list(normalized_targets.dirs),
        exclude=preset.exclude_paths,
        paths_from_stdin=target_params.paths_from_stdin,
        include_dotfiles=target_params.include_dotfiles,
    )


def _build_git_options(git_params: LintGitParams, no_lint_tests: bool) -> LintGitOptions:
    """Return git-discovery options reflecting preset adjustments.

    Args:
        git_params: Parameters describing how git discovery should behave.
        no_lint_tests: Whether test directories should be excluded by default.

    Returns:
        LintGitOptions: Git configuration embedded in :class:`LintOptions`.
    """

    return LintGitOptions(
        changed_only=git_params.changed_only,
        diff_ref=git_params.diff_ref,
        include_untracked=git_params.include_untracked,
        base_branch=git_params.base_branch,
        no_lint_tests=no_lint_tests,
    )


def _build_selection_options(selection: LintSelectionParams) -> LintSelectionOptions:
    """Return lint-selection options captured from CLI dependencies.

    Args:
        selection: Selection parameters describing filters and tool subsets.

    Returns:
        LintSelectionOptions: Normalised selection configuration.
    """

    return LintSelectionOptions(
        filters=list(selection.filters),
        only=list(selection.only),
        language=list(selection.language),
        fix_only=selection.fix_only,
        check_only=selection.check_only,
    )


def _build_output_bundle(
    output: LintOutputGroup,
    display: CLIDisplayOptions,
    artifacts: LintOutputArtifacts,
    preset: NormalPresetResult,
) -> LintOutputBundle:
    """Return the output bundle describing console and report targets.

    Args:
        output: CLI output parameters grouped by rendering/reporting category.
        display: Console display configuration assembled earlier in the flow.
        artifacts: Filesystem artifact destinations requested by the user.
        preset: Preset adjustments that may tweak display behaviour.

    Returns:
        LintOutputBundle: Bundle containing display and summary configuration.
    """

    return LintOutputBundle(
        display=OptionsDisplayOptions(
            verbose=display.verbose,
            quiet=display.quiet,
            no_color=output.rendering.no_color,
            no_emoji=output.rendering.no_emoji,
            output_mode=preset.output_mode,
            debug=output.rendering.debug,
            advice=preset.advice,
        ),
        summary=LintSummaryOptions(
            show_passing=output.reporting.show_passing,
            no_stats=output.reporting.no_stats,
            pr_summary_out=artifacts.pr_summary_out,
            pr_summary_limit=output.summary.pr_summary_limit,
            pr_summary_min_severity=output.summary.pr_summary_min_severity,
            pr_summary_template=output.summary.pr_summary_template,
        ),
    )


def _build_execution_options(
    execution: LintExecutionGroup,
    advanced: LintAdvancedGroup,
    cache_dir: Path,
    use_local_linters: bool,
    effective_jobs: int,
) -> LintExecutionOptions:
    """Return execution options including runtime and formatting overrides.

    Args:
        execution: CLI execution parameters grouped by selection/runtime.
        advanced: Advanced overrides bundled with severity information.
        cache_dir: Resolved cache directory derived from CLI inputs.
        use_local_linters: Whether local linters should be preferred.
        effective_jobs: Finalised job count after preset adjustments.

    Returns:
        LintExecutionOptions: Runtime and formatting configuration for linting.
    """

    runtime = _build_runtime_options(
        execution.runtime,
        cache_dir,
        use_local_linters,
        effective_jobs,
    )
    formatting = _build_formatting_options(advanced.overrides)
    return LintExecutionOptions(runtime=runtime, formatting=formatting)


def _build_runtime_options(
    runtime: LintExecutionRuntimeParams,
    cache_dir: Path,
    use_local_linters: bool,
    effective_jobs: int,
) -> ExecutionRuntimeOptions:
    """Return runtime execution options derived from CLI settings.

    Args:
        runtime: Runtime parameters collected from CLI dependencies.
        cache_dir: Resolved cache directory used for execution caching.
        use_local_linters: Whether the run should prefer local linters.
        effective_jobs: Finalised job count after preset adjustments.

    Returns:
        ExecutionRuntimeOptions: Execution runtime configuration for lint.
    """

    return ExecutionRuntimeOptions(
        jobs=effective_jobs,
        bail=runtime.bail,
        no_cache=runtime.no_cache,
        cache_dir=cache_dir,
        use_local_linters=use_local_linters,
        strict_config=runtime.strict_config,
    )


def _build_formatting_options(overrides: LintOverrideParams) -> ExecutionFormattingOptions:
    """Return formatting options shared across compatible tools.

    Args:
        overrides: Advanced override parameters assembled from CLI flags.

    Returns:
        ExecutionFormattingOptions: Formatting preferences propagated to tools.
    """

    return ExecutionFormattingOptions(
        line_length=overrides.line_length,
        sql_dialect=overrides.sql_dialect,
        python_version=overrides.python_version,
    )


def _build_override_options(advanced: LintAdvancedGroup) -> LintOverrideOptions:
    """Return the override bundle copied from advanced CLI parameters.

    Args:
        advanced: Advanced CLI inputs containing override dataclasses.

    Returns:
        LintOverrideOptions: Override configuration extracted from ``advanced``.
    """

    overrides = advanced.overrides
    severity = advanced.severity
    return LintOverrideOptions(
        complexity=LintComplexityOptions(
            max_complexity=overrides.max_complexity,
            max_arguments=overrides.max_arguments,
        ),
        strictness=LintStrictnessOptions(
            type_checking=overrides.type_checking,
        ),
        severity=LintSeverityOptions(
            bandit_severity=severity.bandit_severity,
            bandit_confidence=severity.bandit_confidence,
            pylint_fail_under=severity.pylint_fail_under,
            sensitivity=severity.sensitivity,
        ),
    )


def _normalize_targets(
    ctx: typer.Context,
    params: LintPathParams,
    *,
    invocation_cwd: Path,
    logger: CLILoggerView,
) -> NormalizedTargets:
    """Return normalised filesystem targets extracted from CLI inputs.

    Args:
        ctx: Typer context providing parameter source metadata.
        params: Path parameters collected from CLI dependencies.
        invocation_cwd: Working directory at invocation time.
        logger: CLI logger used to emit warnings about ignored paths.

    Returns:
        NormalizedTargets: Structured paths, directories, exclusions, and
        ignored pyqa_lint entries.
    """

    paths = _normalize_path_iter(params.paths, invocation_cwd)
    dirs = _normalize_path_iter(params.dirs, invocation_cwd)
    exclude = _normalize_path_iter(params.exclude, invocation_cwd)

    root = _select_root(
        ctx,
        params.root,
        paths,
        invocation_cwd=invocation_cwd,
    )

    paths, ignored_pyqa_lint = _apply_pyqa_lint_filter(paths, root, logger)

    return NormalizedTargets(
        root=root,
        paths=paths,
        dirs=dirs,
        exclude=exclude,
        ignored_pyqa_lint=ignored_pyqa_lint,
    )


def _resolve_artifacts(
    reporting: LintReportingParams,
    *,
    invocation_cwd: Path,
) -> LintOutputArtifacts:
    """Return resolved artifact destinations based on CLI inputs.

    Args:
        reporting: Reporting parameters describing artifact locations.
        invocation_cwd: Working directory at invocation time.

    Returns:
        LintOutputArtifacts: Structured artifact destinations.
    """

    def _normalize(value: Path | None) -> Path | None:
        """Return the normalised path for ``value`` when provided.

        Args:
            value: Optional filesystem path supplied via CLI parameters.

        Returns:
            Path | None: Normalised path anchored to ``invocation_cwd`` or ``None`` when
            ``value`` is not provided.
        """

        if value is None:
            return None
        return _normalize_path(value, invocation_cwd)

    return LintOutputArtifacts(
        report_json=_normalize(reporting.report_json),
        sarif_out=_normalize(reporting.sarif_out),
        pr_summary_out=_normalize(reporting.pr_summary_out),
    )


def _select_root(
    ctx: typer.Context,
    root_option: Path,
    paths: list[Path],
    *,
    invocation_cwd: Path,
) -> Path:
    """Return the effective lint root considering CLI defaults and paths.

    Args:
        ctx: Typer context describing how parameters were provided.
        root_option: Root option supplied via CLI dependency.
        paths: Normalised positional paths supplied to the command.
        invocation_cwd: Working directory used to resolve relative inputs.

    Returns:
        Path: Effective lint root.
    """

    root_source = _parameter_source_name(ctx, "root")
    root = normalize_path(root_option, base_dir=invocation_cwd)
    if root_source not in {"DEFAULT", "DEFAULT_MAP"} or not paths:
        return root

    derived_root = _derive_default_root(paths)
    if derived_root is None:
        return root
    if is_pyqa_lint_workspace(derived_root) or not is_pyqa_lint_workspace(root):
        return derived_root
    return root


def _apply_pyqa_lint_filter(
    paths: list[Path],
    root: Path,
    logger: CLILoggerView,
) -> tuple[list[Path], list[str]]:
    """Return filtered paths and ignored pyqa_lint entries when required.

    Args:
        paths: Candidate filesystem paths supplied by the user.
        root: Effective lint root resolved for the invocation.
        logger: CLI logger responsible for emitting workspace warnings.

    Returns:
        tuple[list[Path], list[str]]: Tuple containing filtered paths and the ignored
        entries referencing ``PYQA_LINT_DIR_NAME`` directories.
    """

    if is_pyqa_lint_workspace(root) or not paths:
        return paths, []

    filtered, ignored = filter_pyqa_lint_paths(paths, root)
    if ignored:
        unique = ", ".join(dict.fromkeys(ignored))
        message = (
            f"Ignoring path(s) {unique}: '{PYQA_LINT_DIR_NAME}' directories are skipped "
            "unless lint runs inside the pyqa_lint workspace."
        )
        logger.warn(message)
    return filtered, ignored


def _build_display_options(rendering: LintOutputParams) -> CLIDisplayOptions:
    """Return CLI display options derived from rendering parameters.

    Args:
        rendering: Rendering parameters captured from CLI inputs.

    Returns:
        CLIDisplayOptions: Structured display toggles for lint execution.
    """

    return CLIDisplayOptions(
        no_emoji=rendering.no_emoji,
        quiet=rendering.quiet,
        verbose=rendering.verbose,
        debug=rendering.debug,
    )


def _effective_jobs(runtime: LintExecutionRuntimeParams) -> int:
    """Return the effective job count considering defaults and overrides.

    Args:
        runtime: Runtime parameters including optional job overrides.

    Returns:
        int: Job count used for lint execution.
    """

    return runtime.jobs if runtime.jobs is not None else default_parallel_jobs()


def _apply_normal_preset(
    *,
    meta: LintMetaParams,
    state: NormalPresetState,
) -> NormalPresetResult:
    """Apply the normal preset adjustments when requested.

    Args:
        meta: Meta parameters containing the normal preset flag.
        state: Mutable preset state recorded before adjustments.

    Returns:
        NormalPresetResult: Updated preset configuration after applying rules.
    """

    updated_exclude = list(state.exclude_paths)
    updated_provided = set(state.provided_flags)
    effective_output = state.output_mode
    effective_advice = state.advice
    effective_no_lint_tests = state.no_lint_tests
    effective_use_local_linters = state.use_local_linters

    if meta.normal:
        if PROVIDED_FLAG_OUTPUT_MODE not in updated_provided:
            effective_output = OUTPUT_MODE_CONCISE
        effective_advice = True
        effective_no_lint_tests = True
        effective_use_local_linters = True
        updated_provided.update(
            {
                PROVIDED_FLAG_OUTPUT_MODE,
                PROVIDED_FLAG_ADVICE,
                PROVIDED_FLAG_EXCLUDE,
                PROVIDED_FLAG_USE_LOCAL_LINTERS,
                PROVIDED_FLAG_NO_LINT_TESTS,
                PROVIDED_FLAG_INTERNAL_LINTERS,
            },
        )

    if effective_no_lint_tests:
        tests_path = Path("tests")
        if tests_path not in updated_exclude:
            updated_exclude.append(tests_path)
        updated_provided.add("exclude")

    return NormalPresetResult(
        output_mode=effective_output,
        advice=effective_advice,
        no_lint_tests=effective_no_lint_tests,
        use_local_linters=effective_use_local_linters,
        exclude_paths=updated_exclude,
        provided_flags=updated_provided,
    )


def _validate_pylint_fail_under(value: float | None) -> None:
    """Ensure ``value`` falls within the accepted pylint fail-under range.

    Args:
        value: Optional pylint fail-under value supplied via CLI.

    Raises:
        typer.BadParameter: If ``value`` is outside the inclusive range 0-10.
    """

    if value is None:
        return
    if not 0 <= value <= 10:
        raise typer.BadParameter("--pylint-fail-under must be between 0 and 10")


def _normalize_path(path: Path, invocation_cwd: Path) -> Path:
    """Return ``path`` resolved relative to ``invocation_cwd`` when needed.

    Args:
        path: Path provided by the caller.
        invocation_cwd: Working directory at invocation time.

    Returns:
        Path: Normalised absolute path.
    """

    return normalize_path(path, base_dir=invocation_cwd)


def _normalize_path_iter(values: Iterable[Path], invocation_cwd: Path) -> list[Path]:
    """Return a list of normalised paths derived from ``values``.

    Args:
        values: Iterable of path values to normalise.
        invocation_cwd: Working directory at invocation time.

    Returns:
        list[Path]: Normalised absolute paths.
    """

    return [normalize_path(value, base_dir=invocation_cwd) for value in values]


def _collect_provided_flags(
    ctx: typer.Context,
    *,
    paths_provided: bool,
    directories: list[Path],
    exclusion_paths: list[Path],
    selection: LintSelectionParams,
) -> set[str]:
    """Return the set of CLI flags explicitly provided by the user.

    Args:
        ctx: Typer context providing parameter source metadata.
        paths_provided: Whether positional paths were supplied.
        directories: Additional directory roots supplied via CLI.
        exclusion_paths: Explicit exclusion paths supplied via CLI.
        selection: Structured selection parameters.

    Returns:
        set[str]: Set of option names provided by the caller.
    """

    tracked = {
        "changed_only",
        "diff_ref",
        "include_untracked",
        "base_branch",
        "paths_from_stdin",
        "dirs",
        "exclude",
        "dotfiles",
        "filters",
        "only",
        "language",
        "normal",
        "check_docstrings",
        "check_suppressions",
        "check_types_strict",
        "check_missing",
        "fix_only",
        "check_only",
        "verbose",
        "quiet",
        "no_color",
        "no_emoji",
        "no_stats",
        PROVIDED_FLAG_OUTPUT_MODE,
        "show_passing",
        "jobs",
        "bail",
        "no_cache",
        "cache_dir",
        "pr_summary_out",
        "pr_summary_limit",
        "pr_summary_min_severity",
        "pr_summary_template",
        PROVIDED_FLAG_USE_LOCAL_LINTERS,
        "line_length",
        "max_complexity",
        "max_arguments",
        "type_checking",
        "bandit_severity",
        "bandit_confidence",
        "pylint_fail_under",
        "sensitivity",
        "sql_dialect",
        PROVIDED_FLAG_ADVICE,
        PROVIDED_FLAG_INTERNAL_LINTERS,
    }
    tracked.update(RUNTIME_CORE_FLAGS)
    tracked.update(RUNTIME_INTERFACE_FLAGS)
    tracked.update(RUNTIME_POLICY_FLAGS)
    tracked.update(RUNTIME_ADDITIONAL_FLAGS)
    provided: set[str] = set()
    for name in tracked:
        source = _parameter_source_name(ctx, name)
        if source not in {"DEFAULT", "DEFAULT_MAP", None}:
            provided.add(name)
    if paths_provided:
        provided.add("paths")
    if directories:
        provided.add("dirs")
    if exclusion_paths:
        provided.add("exclude")
    if selection.filters:
        provided.add("filters")
    if selection.only:
        provided.add("only")
    if selection.language:
        provided.add("language")
    return provided


def _parameter_source_name(ctx: typer.Context, name: str) -> str | None:
    """Return the Typer parameter source name when available.

    Args:
        ctx: Typer context used to resolve parameter sources.
        name: Parameter name whose source should be inspected.

    Returns:
        str | None: Source label or ``None`` when unavailable.
    """

    getter = getattr(ctx, "get_parameter_source", None)
    if not callable(getter):
        return None
    try:
        source = getter(name)
    except TypeError:
        return None
    if source is None:
        return None
    label = getattr(source, "name", None)
    return label if isinstance(label, str) else str(source)


def _derive_default_root(paths: list[Path]) -> Path | None:
    """Return a sensible default root directory given ``paths``.

    Args:
        paths: Candidate paths supplied via CLI arguments.

    Returns:
        Path | None: Derived root directory when available.
    """

    if not paths:
        return None
    candidates = [path if path.is_dir() else path.parent for path in paths]
    if not candidates:
        return None
    common = Path(os.path.commonpath([str(candidate) for candidate in candidates]))
    return common.resolve()


__all__ = [
    "PreparedLintState",
    "prepare_lint_state",
]
