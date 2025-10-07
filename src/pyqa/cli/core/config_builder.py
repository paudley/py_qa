# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Translate CLI options into runtime configuration objects."""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from functools import partial
from pathlib import Path
from typing import Final, cast

from pyqa.core.config.loader import ConfigLoader

from ...config import (
    BanditConfidence,
    BanditLevel,
    Config,
    ExecutionConfig,
    FileDiscoveryConfig,
    OutputConfig,
    SensitivityLevel,
    StrictnessLevel,
)
from ...interfaces.config import ConfigSource
from ._config_builder_constants import (
    DEDUPE_SECTION,
)
from ._config_builder_constants import DEFAULT_TOOL_FILTERS as _DEFAULT_TOOL_FILTERS
from ._config_builder_constants import (
    EXECUTION_SECTION,
    FILE_DISCOVERY_SECTION,
    OUTPUT_SECTION,
    SEVERITY_RULES_KEY,
    TOOL_SETTINGS_KEY,
    LintOptionKey,
)
from ._config_builder_execution import (
    apply_execution_overrides,
    collect_execution_overrides,
)
from ._config_builder_file_discovery import (
    apply_file_discovery_overrides,
    collect_file_discovery_overrides,
)
from ._config_builder_output import apply_output_overrides, collect_output_overrides
from ._config_builder_overrides import (
    ComplexityOverrides,
    SeverityOverrides,
    StrictnessOverrides,
    apply_complexity_overrides,
    apply_severity_overrides,
    apply_strictness_overrides,
    coerce_enum_value,
)
from .options import LintOptions
from .python_version_resolver import resolve_python_version

DEFAULT_TOOL_FILTERS: Final = _DEFAULT_TOOL_FILTERS


def build_config(options: LintOptions, *, sources: Sequence[ConfigSource] | None = None) -> Config:
    """Translate CLI option data into an executable configuration.

    Args:
        options: CLI options resolved from command-line arguments.
        sources: Optional configuration sources overriding the default
            precedence.

    Returns:
        Config: Concrete configuration instance prepared for execution using
        helpers in ``_config_builder_file_discovery``, ``_config_builder_output``
        and ``_config_builder_execution``.
    """

    project_root = options.root.resolve()
    loader = (
        ConfigLoader.for_root(project_root)
        if sources is None
        else ConfigLoader(project_root=project_root, sources=list(sources))
    )
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
        FILE_DISCOVERY_SECTION: file_cfg,
        OUTPUT_SECTION: output_cfg,
        EXECUTION_SECTION: execution_cfg,
        DEDUPE_SECTION: dedupe_cfg,
        SEVERITY_RULES_KEY: list(base_config.severity_rules),
        TOOL_SETTINGS_KEY: {tool: dict(settings) for tool, settings in base_config.tool_settings.items()},
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
        Config: Updated configuration reflecting CLI overrides provided by
        the dataclasses in ``_config_builder_overrides``.

    Raises:
        ValueError: If the CLI-provided override uses an unsupported token.
    """

    has_option = cast(
        Callable[[LintOptionKey], bool],
        partial(_is_option_provided, provided=options.provided),
    )

    severity_overrides = _collect_severity_overrides(options, has_option)
    complexity_overrides = _collect_complexity_overrides(options, has_option)
    strictness_overrides = _collect_strictness_overrides(options, has_option)

    config = apply_severity_overrides(config, severity_overrides)
    config = apply_complexity_overrides(config, complexity_overrides)
    config = apply_strictness_overrides(config, strictness_overrides)
    return config


def _collect_severity_overrides(
    options: LintOptions,
    has_option: Callable[[LintOptionKey], bool],
) -> SeverityOverrides:
    """Return severity overrides derived from CLI arguments."""

    sensitivity = None
    if has_option(LintOptionKey.SENSITIVITY) and options.sensitivity is not None:
        sensitivity = coerce_enum_value(
            options.sensitivity,
            SensitivityLevel,
            "--sensitivity",
        )

    bandit_level = None
    if has_option(LintOptionKey.BANDIT_SEVERITY) and options.bandit_severity is not None:
        bandit_level = coerce_enum_value(
            options.bandit_severity,
            BanditLevel,
            "--bandit-severity",
        )

    bandit_confidence = None
    if has_option(LintOptionKey.BANDIT_CONFIDENCE) and options.bandit_confidence is not None:
        bandit_confidence = coerce_enum_value(
            options.bandit_confidence,
            BanditConfidence,
            "--bandit-confidence",
        )

    pylint_fail_under = None
    if has_option(LintOptionKey.PYLINT_FAIL_UNDER) and options.pylint_fail_under is not None:
        pylint_fail_under = options.pylint_fail_under

    return SeverityOverrides(
        sensitivity=sensitivity,
        bandit_level=bandit_level,
        bandit_confidence=bandit_confidence,
        pylint_fail_under=pylint_fail_under,
    )


def _collect_complexity_overrides(
    options: LintOptions,
    has_option: Callable[[LintOptionKey], bool],
) -> ComplexityOverrides:
    """Return complexity overrides derived from CLI arguments."""

    max_complexity = options.max_complexity if has_option(LintOptionKey.MAX_COMPLEXITY) else None
    max_arguments = options.max_arguments if has_option(LintOptionKey.MAX_ARGUMENTS) else None

    return ComplexityOverrides(
        max_complexity=max_complexity,
        max_arguments=max_arguments,
    )


def _collect_strictness_overrides(
    options: LintOptions,
    has_option: Callable[[LintOptionKey], bool],
) -> StrictnessOverrides:
    """Return strictness overrides derived from CLI arguments."""

    type_checking = None
    if has_option(LintOptionKey.TYPE_CHECKING) and options.type_checking is not None:
        type_checking = coerce_enum_value(
            options.type_checking,
            StrictnessLevel,
            "--type-checking",
        )
    return StrictnessOverrides(type_checking=type_checking)


def _is_option_provided(key: LintOptionKey, *, provided: Collection[str]) -> bool:
    """Return whether a specific CLI option has been explicitly provided.

    Args:
        key: The option identifier to test.
        provided: Collection of option labels supplied by the CLI parser.

    Returns:
        bool: ``True`` when the option was explicitly set.
    """

    return key.value in provided


def _build_file_discovery(
    current: FileDiscoveryConfig,
    options: LintOptions,
    project_root: Path,
) -> FileDiscoveryConfig:
    """Return file discovery configuration updated by CLI overrides.

    The heavy lifting lives in :mod:`pyqa.cli._config_builder_file_discovery`
    where overrides are collected and applied.

    Args:
        current: File discovery configuration sourced from disk.
        options: CLI options to translate into overrides.
        project_root: Absolute project root used for path resolution.

    Returns:
        FileDiscoveryConfig: New configuration instance reflecting overrides.
    """

    overrides = collect_file_discovery_overrides(current, options, project_root)
    return apply_file_discovery_overrides(current, overrides)


def _build_output(
    current: OutputConfig,
    options: LintOptions,
    project_root: Path,
) -> OutputConfig:
    """Return output configuration updated by CLI overrides.

    Delegates to :mod:`pyqa.cli._config_builder_output` helpers for collection
    and application of overrides.

    Args:
        current: Output configuration loaded from disk.
        options: CLI options that may adjust output behaviour.
        project_root: Absolute project root used for filesystem resolution.

    Returns:
        OutputConfig: New configuration instance reflecting overrides.
    """

    has_option = cast(
        Callable[[LintOptionKey], bool],
        partial(_is_option_provided, provided=options.provided),
    )
    overrides = collect_output_overrides(
        current,
        options,
        project_root,
        has_option,
    )
    return apply_output_overrides(current, overrides)


def _build_execution(
    current: ExecutionConfig,
    options: LintOptions,
    project_root: Path,
) -> ExecutionConfig:
    """Return execution configuration updated by CLI overrides.

    Uses :mod:`pyqa.cli._config_builder_execution` to construct the resulting
    configuration fragment.

    Args:
        current: Execution configuration loaded from disk.
        options: CLI options that may alter execution semantics.
        project_root: Absolute project root used for resolving cache paths.

    Returns:
        ExecutionConfig: New configuration instance reflecting overrides.
    """

    has_option = cast(
        Callable[[LintOptionKey], bool],
        partial(_is_option_provided, provided=options.provided),
    )
    overrides = collect_execution_overrides(
        current,
        options,
        project_root,
        has_option,
    )
    return apply_execution_overrides(current, overrides)
