# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Public linting interfaces grouped into focused submodules."""

from __future__ import annotations

from typing import Final

from .logger import CLIDisplayOptions, CLILogger
from .meta import (
    LintMetaParams,
    MetaActionParamsView,
    MetaAnalysisChecksView,
    MetaRuntimeChecksView,
    RuntimeAdditionalChecksView,
    RuntimeCoreChecksView,
    RuntimeInterfaceChecksView,
    RuntimePolicyChecksView,
)
from .options import (
    LintComplexityOptionsView,
    LintExecutionOptions,
    LintGitOptionsView,
    LintOptions,
    LintOptionsView,
    LintOutputBundleView,
    LintOverrideOptionsView,
    LintRuntimeOptions,
    LintSelectionOptionsView,
    LintSeverityOptionsView,
    LintStrictnessOptionsView,
    LintSummaryOptionsView,
    LintTargetOptions,
)
from .state import (
    LintOutputArtifacts,
    LintRunArtifacts,
    LintStateOptions,
    MissingFinding,
    PreparedLintState,
    SuppressionDirective,
    SuppressionRegistry,
)
from .types import LintOptionValue, OutputModeLiteral, PRSummarySeverityLiteral

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
    "LintOptionValue",
    "LintRunArtifacts",
    "LintSelectionOptionsView",
    "LintSeverityOptionsView",
    "LintStateOptions",
    "LintStrictnessOptionsView",
    "LintSummaryOptionsView",
    "LintTargetOptions",
    "MissingFinding",
    "MetaActionParamsView",
    "MetaAnalysisChecksView",
    "MetaRuntimeChecksView",
    "OutputModeLiteral",
    "PRSummarySeverityLiteral",
    "PreparedLintState",
    "RuntimeAdditionalChecksView",
    "RuntimeCoreChecksView",
    "RuntimeInterfaceChecksView",
    "RuntimePolicyChecksView",
    "SuppressionDirective",
    "SuppressionRegistry",
]
