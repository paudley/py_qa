# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared help strings and option aliases for lint CLI dependencies."""

from __future__ import annotations

from typing import Final

from ...update.models import ROOT_OPTION as UPDATE_ROOT_OPTION
from ..literals import OUTPUT_MODE_CONCISE

NORMAL_PRESET_HELP: Final[str] = (
    "Apply the built-in 'normal' lint preset (concise output, advice, no tests, local linters)."
)
EXPLAIN_TOOLS_HELP: Final[str] = "Show the tool selection plan with reasons and exit."
EXPLAIN_TOOLS_JSON_HELP: Final[str] = "Write explain-tools data to PATH as JSON (use '-' for stdout)."
DOCSTRINGS_HELP: Final[str] = "Run the internal docstring quality linter and exit."
SUPPRESSIONS_HELP: Final[str] = "Run the internal suppression checker and exit."
TYPING_HELP: Final[str] = "Run the strict typing checker and exit."
MISSING_HELP: Final[str] = "Run the missing functionality detector and exit."
CLOSURES_HELP: Final[str] = "Run the closure/partial usage checker and exit."
CONDITIONAL_IMPORTS_HELP: Final[str] = (
    "Run the conditional import checker and exit (imports must be hoisted and abstractions live under interfaces)."
)
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

RootOption = UPDATE_ROOT_OPTION

__all__ = [
    "ADVICE_HELP",
    "BANDIT_CONFIDENCE_HELP",
    "BANDIT_SEVERITY_HELP",
    "CACHE_DIR_HELP",
    "CACHE_HELP",
    "CHECK_DI_HELP",
    "CHECK_INTERFACES_HELP",
    "CHECK_MODULE_DOCS_HELP",
    "CONDITIONAL_IMPORTS_HELP",
    "CLOSURES_HELP",
    "COPYRIGHT_HELP",
    "DOCSTRINGS_HELP",
    "EXPLAIN_TOOLS_HELP",
    "EXPLAIN_TOOLS_JSON_HELP",
    "FETCH_ALL_TOOLS_HELP",
    "FILE_SIZE_HELP",
    "FILTER_HELP",
    "JOBS_HELP",
    "LICENSE_HEADER_HELP",
    "LINE_LENGTH_HELP",
    "MAX_ARGUMENTS_HELP",
    "MAX_COMPLEXITY_HELP",
    "MISSING_HELP",
    "NORMAL_PRESET_HELP",
    "OUTPUT_MODE_HELP",
    "OUTPUT_MODE_CONCISE",
    "PR_SUMMARY_MIN_SEVERITY_HELP",
    "PR_SUMMARY_OUT_HELP",
    "PR_SUMMARY_TEMPLATE_HELP",
    "PYTHON_HYGIENE_HELP",
    "PYTHON_VERSION_HELP",
    "PYQA_PYTHON_HYGIENE_HELP",
    "PYQA_RULES_HELP",
    "PYLINT_FAIL_UNDER_HELP",
    "REPORT_JSON_HELP",
    "RootOption",
    "SARIF_HELP",
    "SCHEMA_SYNC_HELP",
    "SENSITIVITY_HELP",
    "SHOW_VALID_SUPPRESSIONS_HELP",
    "SIGNATURES_HELP",
    "SQL_DIALECT_HELP",
    "STRICT_CONFIG_HELP",
    "TOOL_INFO_HELP",
    "TYPE_CHECKING_HELP",
    "TYPING_HELP",
    "USE_LOCAL_LINTERS_HELP",
    "VALIDATE_SCHEMA_HELP",
    "VALUE_TYPES_GENERAL_HELP",
]
