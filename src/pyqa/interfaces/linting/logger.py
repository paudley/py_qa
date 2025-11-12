# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""CLI logging and display option interfaces used by lint tooling."""

from __future__ import annotations

from abc import abstractmethod
from typing import Protocol, runtime_checkable

from rich.console import Console

from .types import OutputModeLiteral


@runtime_checkable
class CLILogger(Protocol):
    """Protocol describing logging helpers supplied by the CLI layer."""

    __slots__ = ()

    @abstractmethod
    def fail(self, message: str) -> None:
        """Render a failure ``message`` honouring CLI presentation preferences.

        Args:
            message: Message string describing the failure condition.
        """

    @abstractmethod
    def warn(self, message: str) -> None:
        """Render a warning ``message`` honouring CLI presentation preferences.

        Args:
            message: Message string describing the warning condition.
        """

    @abstractmethod
    def ok(self, message: str) -> None:
        """Render a success ``message`` honouring CLI presentation preferences.

        Args:
            message: Message string describing the success condition.
        """

    @abstractmethod
    def echo(self, message: str) -> None:
        """Write ``message`` to stdout using the CLI output mechanism.

        Args:
            message: Message string sent to standard output.
        """

    @abstractmethod
    def debug(self, message: str) -> None:
        """Emit a debug ``message`` when debug logging is enabled.

        Args:
            message: Message string describing the debug condition.
        """

    @property
    @abstractmethod
    def console(self) -> Console:
        """Return the Rich console used for rendering CLI output.

        Returns:
            Console: Rich console instance bound to the logger.
        """


@runtime_checkable
class CLIDisplayOptions(Protocol):
    """Protocol describing CLI display toggles shared with linters."""

    __slots__ = ()

    @property
    @abstractmethod
    def no_emoji(self) -> bool:
        """Return ``True`` when emoji output is disabled.

        Returns:
            bool: ``True`` when emoji output is disabled.
        """

    @property
    @abstractmethod
    def quiet(self) -> bool:
        """Return ``True`` when quiet output is enabled.

        Returns:
            bool: ``True`` when quiet output is enabled.
        """

    @property
    @abstractmethod
    def verbose(self) -> bool:
        """Return ``True`` when verbose output is enabled.

        Returns:
            bool: ``True`` when verbose output is enabled.
        """

    @property
    @abstractmethod
    def debug(self) -> bool:
        """Return ``True`` when debug output is enabled.

        Returns:
            bool: ``True`` when debug output is enabled.
        """

    @property
    @abstractmethod
    def no_color(self) -> bool:
        """Return ``True`` when colour output is disabled.

        Returns:
            bool: ``True`` when colour output is disabled.
        """

    @property
    @abstractmethod
    def output_mode(self) -> OutputModeLiteral:
        """Return the configured output mode literal.

        Returns:
            OutputModeLiteral: Output mode literal requested by the user.
        """

    @property
    @abstractmethod
    def advice(self) -> bool:
        """Return ``True`` when advisory output is enabled.

        Returns:
            bool: ``True`` when advisory output is enabled.
        """

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


__all__ = [
    "CLIDisplayOptions",
    "CLILogger",
]
