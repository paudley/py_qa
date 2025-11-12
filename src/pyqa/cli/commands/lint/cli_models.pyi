# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Type hints describing lint CLI models and parameters."""

from __future__ import annotations

from .literals import (
    BanditLevelLiteral,
    OutputModeLiteral,
    PRSummarySeverityLiteral,
    SensitivityLiteral,
    StrictnessLiteral,
)
from .params import (
    LintAdvancedGroup,
    LintCLIInputs,
    LintExecutionGroup,
    LintOutputGroup,
    LintTargetGroup,
)

ADVICE_HELP: str
BANDIT_CONFIDENCE_HELP: str
BANDIT_LEVEL_CHOICES: tuple[BanditLevelLiteral, ...]
BANDIT_SEVERITY_HELP: str
CACHE_DIR_HELP: str
DOCSTRINGS_HELP: str
SUPPRESSIONS_HELP: str
TYPING_HELP: str
CLOSURES_HELP: str
SIGNATURES_HELP: str
CACHE_HELP: str
PYQA_RULES_HELP: str
FETCH_ALL_TOOLS_HELP: str
FILTER_HELP: str
JOBS_HELP: str
LINE_LENGTH_HELP: str
NORMAL_PRESET_HELP: str
OUTPUT_MODE_CHOICES: tuple[OutputModeLiteral, ...]
OUTPUT_MODE_CONCISE: OutputModeLiteral
OUTPUT_MODE_HELP: str
PR_SUMMARY_MIN_SEVERITY_HELP: str
PR_SUMMARY_OUT_HELP: str
PR_SUMMARY_SEVERITIES: tuple[PRSummarySeverityLiteral, ...]
PR_SUMMARY_TEMPLATE_HELP: str
PYLINT_FAIL_UNDER_HELP: str
REPORT_JSON_HELP: str
SENSITIVITY_CHOICES: tuple[SensitivityLiteral, ...]
SENSITIVITY_HELP: str
STRICTNESS_CHOICES: tuple[StrictnessLiteral, ...]
STRICT_CONFIG_HELP: str
TOOL_INFO_HELP: str
TYPE_CHECKING_HELP: str
USE_LOCAL_LINTERS_HELP: str
VALIDATE_SCHEMA_HELP: str

class LintDisplayOptions:
    """Public display toggles exposed by the lint CLI."""

    no_emoji: bool
    quiet: bool
    verbose: bool
    debug: bool

    def __init__(self, *, no_emoji: bool, quiet: bool, verbose: bool, debug: bool) -> None:
        """Initialise display toggles for the CLI.

        Args:
            no_emoji: Flag disabling emoji output.
            quiet: Flag minimising console output.
            verbose: Flag enabling verbose console output.
            debug: Flag enabling debug output.
        """
        ...

def _build_lint_cli_inputs(
    targets: LintTargetGroup,
    execution: LintExecutionGroup,
    output: LintOutputGroup,
    advanced: LintAdvancedGroup,
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
    ...
