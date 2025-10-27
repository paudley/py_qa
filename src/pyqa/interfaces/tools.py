# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Protocols describing tool configuration structures shared with the CLI."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from functools import singledispatch
from typing import Final, Literal, NoReturn, Protocol, TypeAlias, runtime_checkable

from pyqa.interfaces.discovery import DiscoveryOptions

from .common import CacheControlOptions

StrictnessLiteral: TypeAlias = Literal["lenient", "standard", "strict"]
STRICT_PROFILE: Final[str] = "strict"
BanditLevelLiteral: TypeAlias = Literal["low", "medium", "high"]
SensitivityLiteral: TypeAlias = Literal["low", "medium", "high", "maximum"]


@singledispatch
def _enum_label(value: BanditLevelLiteral | str | None) -> str | None:
    """Return the value unchanged when already string-like.

    Args:
        value: Label value provided by the caller.

    Returns:
        str | None: String label suitable for serialization.
    """

    return value


@_enum_label.register
def _(value: Enum) -> str:
    """Return the string representation of enum values used in severity mapping.

    Args:
        value: Enum instance produced by catalog data.

    Returns:
        str: String form of the enum value.
    """

    raw = value.value
    return raw if isinstance(raw, str) else str(raw)


def _unimplemented_tool_option(method: str) -> NoReturn:
    """Raise :class:`NotImplementedError` for abstract tool option accessors.

    Args:
        method: Qualified method name displayed in the error message.

    Raises:
        NotImplementedError: Always raised to indicate missing implementation.
    """

    raise NotImplementedError(f"{method} must be implemented by concrete tool configurations")


@runtime_checkable
class RuntimeOptions(CacheControlOptions, Protocol):
    """Execution runtime configuration shared across tool integrations.

    Attributes:
        jobs: Maximum number of concurrent jobs or ``None`` when unspecified.
        bail: Flag indicating whether execution should abort on the first failure.
        use_local_linters: Flag indicating whether locally installed linters may be used.
        strict_config: Flag indicating whether strict configuration validation is enforced.
    """

    @property
    def jobs(self) -> int | None:
        """Return the maximum number of concurrent jobs or ``None`` when unlimited.

        Returns:
            int | None: Maximum concurrent job count or ``None`` when unlimited.
        """

        return _unimplemented_tool_option("RuntimeOptions.jobs")

    @property
    def bail(self) -> bool:
        """Return whether execution should abort on the first failure.

        Returns:
            bool: ``True`` when the run should stop on the first failure.
        """

        return _unimplemented_tool_option("RuntimeOptions.bail")

    @property
    def use_local_linters(self) -> bool:
        """Return whether locally installed linters may be used.

        Returns:
            bool: ``True`` when locally installed linters may be used.
        """

        return _unimplemented_tool_option("RuntimeOptions.use_local_linters")

    @property
    def strict_config(self) -> bool:
        """Return whether strict configuration validation is enforced.

        Returns:
            bool: ``True`` when strict configuration validation is enforced.
        """

        return _unimplemented_tool_option("RuntimeOptions.strict_config")

    def concurrency_enabled(self) -> bool:
        """Return ``True`` when more than one concurrent job is permitted.

        Returns:
            bool: ``True`` when the job count exceeds one.
        """

        jobs = self.jobs
        return jobs is not None and jobs > 1


@runtime_checkable
class FormattingOptions(Protocol):
    """Formatting overrides propagated to compatible tooling.

    Attributes:
        line_length: Maximum permitted formatted line length.
        sql_dialect: SQL dialect identifier requested by the user.
        python_version: Target Python version string when provided.
    """

    @property
    def line_length(self) -> int:
        """Return the maximum permitted formatted line length.

        Returns:
            int: Maximum formatted line length in characters.
        """

        return _unimplemented_tool_option("ExecutionOptions.runtime")

    @property
    def sql_dialect(self) -> str:
        """Return the SQL dialect identifier requested by the user.

        Returns:
            str: SQL dialect identifier requested by the user.
        """

        return _unimplemented_tool_option("ExecutionOptions.formatting")

    @property
    def python_version(self) -> str | None:
        """Return the target Python version string when provided.

        Returns:
            str | None: Target Python version or ``None`` when unspecified.
        """

        return _unimplemented_tool_option("ExecutionOptions.line_length")

    def has_python_target(self) -> bool:
        """Return ``True`` when a target Python version has been specified.

        Returns:
            bool: ``True`` when a target Python version is supplied.
        """

        return self.python_version is not None

    def as_dict(self) -> dict[str, int | str | None]:
        """Return a mapping describing the formatting overrides.

        Returns:
            dict[str, int | str | None]: Mapping of formatting attributes.
        """

        return {
            "line_length": self.line_length,
            "sql_dialect": self.sql_dialect,
            "python_version": self.python_version,
        }


@runtime_checkable
class ExecutionOptions(Protocol):
    """Execution options bundle exposed to tooling.

    Attributes:
        runtime: Runtime options inherited from the CLI configuration.
        formatting: Formatting overrides propagated to tooling.
        line_length: Maximum permitted line length in characters.
        sql_dialect: SQL dialect requested for the tooling execution.
        python_version: Target Python version string when provided.
    """

    @property
    def runtime(self) -> RuntimeOptions:
        """Return runtime options inherited from the CLI configuration.

        Returns:
            RuntimeOptions: Runtime options inherited from the CLI configuration.
        """
        return _unimplemented_tool_option("ExecutionOptions.sql_dialect")

    @property
    def formatting(self) -> FormattingOptions:
        """Return formatting overrides propagated to tooling.

        Returns:
            FormattingOptions: Formatting overrides propagated to tooling.
        """
        return _unimplemented_tool_option("ExecutionOptions.python_version")

    @property
    def line_length(self) -> int:
        """Return the maximum permitted line length in characters.

        Returns:
            int: Maximum permitted line length in characters.
        """
        raise NotImplementedError

    @property
    def sql_dialect(self) -> str:
        """Return the SQL dialect requested for the tooling execution.

        Returns:
            str: SQL dialect requested for the tooling execution.
        """
        raise NotImplementedError

    @property
    def python_version(self) -> str | None:
        """Return the target Python version string when provided.

        Returns:
            str | None: Target Python version or ``None`` when unspecified.
        """
        raise NotImplementedError

    def effective_line_length(self) -> int:
        """Return the effective line length applied to tooling execution.

        Returns:
            int: Line length applied to the tooling invocation.
        """

        return self.line_length

    def summary(self) -> tuple[RuntimeOptions, FormattingOptions, int, str, str | None]:
        """Return a tuple describing execution overrides.

        Returns:
            tuple[RuntimeOptions, FormattingOptions, int, str, str | None]:
                Runtime options, formatting overrides, line length, SQL dialect, and Python version.
        """

        return (
            self.runtime,
            self.formatting,
            self.line_length,
            self.sql_dialect,
            self.python_version,
        )


@runtime_checkable
class ComplexityOptions(Protocol):
    """Shared complexity thresholds consulted by tool builders.

    Attributes:
        max_complexity: Maximum cyclomatic complexity threshold.
        max_arguments: Maximum function argument count permitted.
    """

    @property
    def max_complexity(self) -> int | None:
        """Return the maximum cyclomatic complexity threshold.

        Returns:
            int | None: Maximum cyclomatic complexity threshold or ``None``.
        """

        raise NotImplementedError

    @property
    def max_arguments(self) -> int | None:
        """Return the maximum function argument count permitted.

        Returns:
            int | None: Maximum positional argument count or ``None``.
        """

        raise NotImplementedError

    def has_limits(self) -> bool:
        """Return ``True`` when at least one complexity threshold is enforced.

        Returns:
            bool: ``True`` if either complexity or argument limits are set.
        """

        return self.max_complexity is not None or self.max_arguments is not None

    def limits_tuple(self) -> tuple[int | None, int | None]:
        """Return a tuple describing complexity and argument limits.

        Returns:
            tuple[int | None, int | None]: Pair containing complexity and argument thresholds.
        """

        return (self.max_complexity, self.max_arguments)


@runtime_checkable
class SeverityOptions(Protocol):
    """Severity overrides required by catalog command builders.

    Attributes:
        bandit_level: Minimum Bandit severity enforced by the run.
        bandit_confidence: Minimum Bandit confidence enforced by the run.
        pylint_fail_under: pylint score threshold that triggers failure.
        max_warnings: Maximum allowed warning count.
        sensitivity: Repository sensitivity profile label.
    """

    @property
    def bandit_level(self) -> BanditLevelLiteral | Enum | str:
        """Return the minimum Bandit severity enforced by the run.

        Returns:
            BanditLevelLiteral | Enum | str: Minimum Bandit severity enforced by the run.
        """

        raise NotImplementedError

    @property
    def bandit_confidence(self) -> BanditLevelLiteral | Enum | str:
        """Return the minimum Bandit confidence enforced by the run.

        Returns:
            BanditLevelLiteral | Enum | str: Minimum Bandit confidence enforced by the run.
        """

        raise NotImplementedError

    @property
    def pylint_fail_under(self) -> float | None:
        """Return the pylint score threshold that triggers failure.

        Returns:
            float | None: pylint score threshold that triggers failure.
        """

        raise NotImplementedError

    @property
    def max_warnings(self) -> int | None:
        """Return the maximum allowed warning count.

        Returns:
            int | None: Maximum warning count before failure.
        """

        raise NotImplementedError

    @property
    def sensitivity(self) -> SensitivityLiteral | None:
        """Return the repository sensitivity profile label.

        Returns:
            SensitivityLiteral | None: Repository sensitivity profile label.
        """

        raise NotImplementedError

    def has_warning_limits(self) -> bool:
        """Return ``True`` when warning or scoring limits are configured.

        Returns:
            bool: ``True`` when warning or score thresholds are provided.
        """

        return (self.max_warnings is not None) or (self.pylint_fail_under is not None)

    def thresholds(self) -> dict[str, float | int | str | None]:
        """Return a mapping describing severity thresholds and limits.

        Returns:
            dict[str, float | int | str | None]: Threshold information keyed by metric.
        """

        return {
            "bandit_level": _enum_label(self.bandit_level),
            "bandit_confidence": _enum_label(self.bandit_confidence),
            "pylint_fail_under": self.pylint_fail_under,
            "max_warnings": self.max_warnings,
            "sensitivity": self.sensitivity,
        }


@runtime_checkable
class StrictnessOptions(Protocol):
    """Strictness toggles required by catalog references.

    Attributes:
        type_checking: Type-checking strictness level.
    """

    @property
    def type_checking(self) -> StrictnessLiteral | None:
        """Return the configured type-checking strictness level.

        Returns:
            StrictnessLiteral | None: Configured type-checking strictness level.
        """

        raise NotImplementedError

    def has_type_checking(self) -> bool:
        """Return ``True`` when a type-checking profile is configured.

        Returns:
            bool: ``True`` when ``type_checking`` is not ``None``.
        """

        return self.type_checking is not None

    def is_strict(self) -> bool:
        """Return ``True`` when strict type-checking is requested.

        Returns:
            bool: ``True`` when the strict type-checking profile is active.
        """

        return self.type_checking == STRICT_PROFILE


@runtime_checkable
class FileDiscoveryOptions(DiscoveryOptions, Protocol):
    """Filesystem discovery parameters used during planning."""

    __slots__ = ()


@runtime_checkable
class OutputOptions(Protocol):
    """Output configuration shared across tooling integrations.

    Attributes:
        tool_filters: Mapping of tool names to filter tokens.
        color: Flag indicating whether ANSI colouring is enabled.
        emoji: Flag indicating whether emoji output is enabled.
    """

    @property
    def tool_filters(self) -> Mapping[str, Sequence[str]]:
        """Return the mapping of tool names to filter tokens.

        Returns:
            Mapping[str, Sequence[str]]: Mapping of tool names to filter tokens.
        """

        raise NotImplementedError

    @property
    def color(self) -> bool:
        """Return whether ANSI colouring is enabled.

        Returns:
            bool: ``True`` when ANSI colouring is enabled.
        """

        raise NotImplementedError

    @property
    def emoji(self) -> bool:
        """Return whether emoji output is enabled.

        Returns:
            bool: ``True`` when emoji output is enabled.
        """

        raise NotImplementedError

    def has_filters(self) -> bool:
        """Return ``True`` when at least one tool filter is configured.

        Returns:
            bool: ``True`` when any tool filter collection contains entries.
        """

        return any(self.tool_filters.values())

    def summary(self) -> tuple[Mapping[str, Sequence[str]], bool, bool]:
        """Return a tuple describing output configuration flags.

        Returns:
            tuple[Mapping[str, Sequence[str]], bool, bool]: Tool filters, colour flag, and emoji flag.
        """

        return (self.tool_filters, self.color, self.emoji)


@runtime_checkable
class ToolConfiguration(Protocol):
    """Aggregate configuration contract accepted by :class:`ToolContext`.

    Attributes:
        execution: Execution configuration accessible to tooling.
        complexity: Complexity thresholds inherited from CLI configuration.
        severity: Severity overrides inherited from CLI configuration.
        strictness: Strictness overrides inherited from CLI configuration.
        file_discovery: Optional discovery overrides.
        output: Output configuration used by tooling.
    """

    @property
    def execution(self) -> ExecutionOptions:
        """Return the execution configuration accessible to tooling.

        Returns:
            ExecutionOptions: Execution configuration accessible to tooling.
        """

        raise NotImplementedError

    @property
    def complexity(self) -> ComplexityOptions:
        """Return the complexity thresholds inherited from the CLI configuration.

        Returns:
            ComplexityOptions: Complexity thresholds inherited from the CLI configuration.
        """

        raise NotImplementedError

    @property
    def severity(self) -> SeverityOptions:
        """Return severity overrides inherited from the CLI configuration.

        Returns:
            SeverityOptions: Severity overrides inherited from the CLI configuration.
        """

        raise NotImplementedError

    @property
    def strictness(self) -> StrictnessOptions:
        """Return strictness overrides inherited from the CLI configuration.

        Returns:
            StrictnessOptions: Strictness overrides inherited from the CLI configuration.
        """

        raise NotImplementedError

    @property
    def file_discovery(self) -> FileDiscoveryOptions | None:
        """Return optional discovery overrides available to tooling.

        Returns:
            FileDiscoveryOptions | None: Optional discovery overrides.
        """

        raise NotImplementedError

    @property
    def output(self) -> OutputOptions:
        """Return the output configuration used by tooling.

        Returns:
            OutputOptions: Output configuration used by tooling.
        """

        raise NotImplementedError

    def has_file_discovery(self) -> bool:
        """Return ``True`` when file discovery overrides have been supplied.

        Returns:
            bool: ``True`` when discovery overrides are provided.
        """

        return self.file_discovery is not None

    def configuration_tuple(
        self,
    ) -> tuple[
        ExecutionOptions,
        ComplexityOptions,
        SeverityOptions,
        StrictnessOptions,
        FileDiscoveryOptions | None,
        OutputOptions,
    ]:
        """Return a tuple summarising the tool configuration segments.

        Returns:
            tuple[
                ExecutionOptions,
                ComplexityOptions,
                SeverityOptions,
                StrictnessOptions,
                FileDiscoveryOptions | None,
                OutputOptions,
            ]: Tuple containing the key configuration sections in order.
        """

        return (
            self.execution,
            self.complexity,
            self.severity,
            self.strictness,
            self.file_discovery,
            self.output,
        )


__all__: Final = [
    "BanditLevelLiteral",
    "ComplexityOptions",
    "ExecutionOptions",
    "FileDiscoveryOptions",
    "FormattingOptions",
    "OutputOptions",
    "RuntimeOptions",
    "SensitivityLiteral",
    "SeverityOptions",
    "StrictnessLiteral",
    "StrictnessOptions",
    "ToolConfiguration",
]
