# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Protocols describing tool configuration structures shared with the CLI."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Final, Literal, Protocol, TypeAlias, runtime_checkable

from pyqa.interfaces.discovery import DiscoveryOptions

StrictnessLiteral: TypeAlias = Literal["lenient", "standard", "strict"]
BanditLevelLiteral: TypeAlias = Literal["low", "medium", "high"]
SensitivityLiteral: TypeAlias = Literal["low", "medium", "high", "maximum"]


@runtime_checkable
class RuntimeOptions(Protocol):
    """Execution runtime configuration shared across tool integrations."""

    @property
    def jobs(self) -> int | None:
        """Return the parallelism level requested for the tool.

        Returns:
            int | None: Maximum number of concurrent jobs or ``None`` when unspecified.
        """
        raise NotImplementedError

    @property
    def bail(self) -> bool:
        """Return whether execution should abort on the first failure.

        Returns:
            bool: ``True`` when execution should bail on the first error.
        """
        raise NotImplementedError

    @property
    def no_cache(self) -> bool:
        """Return whether caching should be disabled for the tool run.

        Returns:
            bool: ``True`` when caching should be bypassed.
        """
        raise NotImplementedError

    @property
    def cache_dir(self) -> Path:
        """Return the repository-local directory used for tool caches.

        Returns:
            Path: Filesystem path used for tool caches.
        """
        raise NotImplementedError

    @property
    def use_local_linters(self) -> bool:
        """Return whether locally installed linters should be preferred.

        Returns:
            bool: ``True`` when local linters may be used.
        """
        raise NotImplementedError

    @property
    def strict_config(self) -> bool:
        """Return whether strict configuration validation must be enforced.

        Returns:
            bool: ``True`` when configuration validation is strict.
        """
        raise NotImplementedError


@runtime_checkable
class FormattingOptions(Protocol):
    """Formatting overrides propagated to compatible tooling."""

    @property
    def line_length(self) -> int:
        """Return the maximum permitted formatted line length.

        Returns:
            int: Maximum permitted line length in characters.
        """
        raise NotImplementedError

    @property
    def sql_dialect(self) -> str:
        """Return the SQL dialect identifier requested by the user.

        Returns:
            str: SQL dialect identifier requested by the user.
        """
        raise NotImplementedError

    @property
    def python_version(self) -> str | None:
        """Return the target Python version requested for tooling.

        Returns:
            str | None: Target Python version string when provided.
        """
        raise NotImplementedError


@runtime_checkable
class ExecutionOptions(Protocol):
    """Execution options bundle exposed to tooling."""

    @property
    def runtime(self) -> RuntimeOptions:
        """Return runtime options inherited from the CLI configuration.

        Returns:
            RuntimeOptions: Runtime configuration used by tooling integrations.
        """
        raise NotImplementedError

    @property
    def formatting(self) -> FormattingOptions:
        """Return formatting overrides propagated to tooling.

        Returns:
            FormattingOptions: Formatting configuration for tooling integrations.
        """
        raise NotImplementedError

    @property
    def line_length(self) -> int:
        """Return the maximum line length enforced by the execution profile.

        Returns:
            int: Maximum permitted line length in characters.
        """
        raise NotImplementedError

    @property
    def sql_dialect(self) -> str:
        """Return the SQL dialect enforced by the execution profile.

        Returns:
            str: SQL dialect requested for the tooling execution.
        """
        raise NotImplementedError

    @property
    def python_version(self) -> str | None:
        """Return the target Python version requested for tooling.

        Returns:
            str | None: Target Python version string when provided.
        """
        raise NotImplementedError


@runtime_checkable
class ComplexityOptions(Protocol):
    """Shared complexity thresholds consulted by tool builders."""

    @property
    def max_complexity(self) -> int | None:
        """Return the maximum allowed cyclomatic complexity.

        Returns:
            int | None: Maximum cyclomatic complexity threshold.
        """
        raise NotImplementedError

    @property
    def max_arguments(self) -> int | None:
        """Return the maximum allowed function argument count.

        Returns:
            int | None: Maximum positional argument count permitted.
        """
        raise NotImplementedError


@runtime_checkable
class SeverityOptions(Protocol):
    """Severity overrides required by catalog command builders."""

    @property
    def bandit_level(self) -> BanditLevelLiteral | Enum | str:
        """Return the minimum Bandit severity enforced by the run.

        Returns:
            BanditLevelLiteral | Enum | str: Bandit severity threshold.
        """
        raise NotImplementedError

    @property
    def bandit_confidence(self) -> BanditLevelLiteral | Enum | str:
        """Return the minimum Bandit confidence enforced by the run.

        Returns:
            BanditLevelLiteral | Enum | str: Bandit confidence threshold.
        """
        raise NotImplementedError

    @property
    def pylint_fail_under(self) -> float | None:
        """Return the pylint score threshold that triggers failure.

        Returns:
            float | None: pylint fail-under score threshold.
        """
        raise NotImplementedError

    @property
    def max_warnings(self) -> int | None:
        """Return the maximum allowed warning count.

        Returns:
            int | None: Maximum warning allowance.
        """
        raise NotImplementedError

    @property
    def sensitivity(self) -> SensitivityLiteral | None:
        """Return the repository sensitivity profile.

        Returns:
            SensitivityLiteral | None: Repository sensitivity profile label.
        """
        raise NotImplementedError


@runtime_checkable
class StrictnessOptions(Protocol):
    """Strictness toggles required by catalog references."""

    @property
    def type_checking(self) -> StrictnessLiteral | None:
        """Return the type-checking strictness profile.

        Returns:
            StrictnessLiteral | None: Type-checking strictness level.
        """
        raise NotImplementedError

    def has_type_checking(self) -> bool:
        """Return ``True`` when a type-checking profile is configured.

        Returns:
            bool: ``True`` when ``type_checking`` is not ``None``.
        """

        return self.type_checking is not None


@runtime_checkable
class FileDiscoveryOptions(DiscoveryOptions, Protocol):
    """Filesystem discovery parameters used during planning."""

    __slots__ = ()


@runtime_checkable
class OutputOptions(Protocol):
    """Output configuration shared across tooling integrations."""

    @property
    def tool_filters(self) -> Mapping[str, Sequence[str]]:
        """Return suppression filters applied per tool.

        Returns:
            Mapping[str, Sequence[str]]: Mapping of tool names to filter tokens.
        """
        raise NotImplementedError

    @property
    def color(self) -> bool:
        """Return whether coloured output should be emitted.

        Returns:
            bool: ``True`` when ANSI colouring is enabled.
        """
        raise NotImplementedError

    @property
    def emoji(self) -> bool:
        """Return whether emoji output should be emitted.

        Returns:
            bool: ``True`` when emoji output is enabled.
        """
        raise NotImplementedError

    def has_filters(self) -> bool:
        """Return ``True`` when at least one tool filter is configured.

        Returns:
            bool: ``True`` when ``tool_filters`` is non-empty.
        """

        return any(self.tool_filters.values())


@runtime_checkable
class ToolConfiguration(Protocol):
    """Aggregate configuration contract accepted by :class:`ToolContext`."""

    @property
    def execution(self) -> ExecutionOptions:
        """Return execution options inherited from the CLI configuration.

        Returns:
            ExecutionOptions: Execution configuration accessible to tooling.
        """
        raise NotImplementedError

    @property
    def complexity(self) -> ComplexityOptions:
        """Return complexity thresholds inherited from the CLI configuration.

        Returns:
            ComplexityOptions: Complexity thresholds for tooling.
        """
        raise NotImplementedError

    @property
    def severity(self) -> SeverityOptions:
        """Return severity overrides inherited from the CLI configuration.

        Returns:
            SeverityOptions: Severity overrides for tooling.
        """
        raise NotImplementedError

    @property
    def strictness(self) -> StrictnessOptions:
        """Return strictness settings inherited from the CLI configuration.

        Returns:
            StrictnessOptions: Strictness overrides for tooling.
        """
        raise NotImplementedError

    @property
    def file_discovery(self) -> FileDiscoveryOptions | None:
        """Return file discovery overrides when available.

        Returns:
            FileDiscoveryOptions | None: Optional discovery overrides.
        """
        raise NotImplementedError

    @property
    def output(self) -> OutputOptions:
        """Return output configuration inherited from the CLI configuration.

        Returns:
            OutputOptions: Output configuration used by tooling.
        """
        raise NotImplementedError


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
