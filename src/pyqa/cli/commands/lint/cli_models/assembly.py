# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Assembly helpers that combine dependency groups for the lint CLI."""

from __future__ import annotations

from typing import Annotated

from ....core.shared import Depends
from ..params import (
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
)
from .meta import _meta_params_dependency
from .output import _output_params_dependency, _reporting_params_dependency, _summary_params_dependency
from .overrides import _override_params_dependency
from .runtime import _execution_runtime_dependency
from .selection import _selection_params_dependency
from .severity import _severity_params_dependency
from .targets import _git_params_dependency, _path_params_dependency


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
    """Return the advanced lint configuration group.

    Args:
        overrides: Structured override parameters.
        severity: Structured severity parameters.
        meta: Structured meta-parameter configuration.

    Returns:
        LintAdvancedGroup: Aggregated advanced configuration for lint.
    """

    return LintAdvancedGroup(overrides=overrides, severity=severity, meta=meta)


def _build_lint_cli_inputs(
    targets: Annotated[LintTargetGroup, Depends(_build_target_group)],
    execution: Annotated[LintExecutionGroup, Depends(_build_execution_group)],
    output: Annotated[LintOutputGroup, Depends(_build_output_group)],
    advanced: Annotated[LintAdvancedGroup, Depends(_build_advanced_group)],
) -> LintCLIInputs:
    """Construct structured lint CLI inputs from dependency groups.

    Args:
        targets: Target parameters resolved from CLI options.
        execution: Execution parameters resolved from CLI options.
        output: Output parameters resolved from CLI options.
        advanced: Advanced lint parameters resolved from CLI options.

    Returns:
        LintCLIInputs: Consolidated lint CLI configuration.
    """

    return LintCLIInputs(targets=targets, execution=execution, output=output, advanced=advanced)


__all__ = [
    "_build_advanced_group",
    "_build_execution_group",
    "_build_lint_cli_inputs",
    "_build_output_group",
    "_build_target_group",
]
