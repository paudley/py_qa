# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Reusable tool protocol definitions and adapters."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, NoReturn, Protocol, runtime_checkable

from pyqa.core.models import Diagnostic, RawDiagnostic, ToolOutcome

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .base import ToolContext


def _protocol_not_implemented(identifier: str) -> NoReturn:
    """Raise :class:`NotImplementedError` for abstract protocol methods.

    Args:
        identifier: Fully qualified method identifier used in the error message.

    Returns:
        NoReturn: This helper never returns because it always raises an error.

    Raises:
        NotImplementedError: Always raised to highlight missing implementations.
    """

    raise NotImplementedError(f"{identifier} must be implemented by conforming objects")


@runtime_checkable
class Parser(Protocol):
    """Protocol implemented by output parsers."""

    @abstractmethod
    def parse(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Parse output streams produced by an external tool.

        Implementations must return diagnostics or raw diagnostic payloads derived from
        the provided ``stdout``/``stderr`` sequences.

        Args:
            stdout: Lines emitted on standard output by the external tool.
            stderr: Lines emitted on standard error by the external tool.
            context: Tool execution context describing configuration and files.

        Returns:
            Sequence[RawDiagnostic | Diagnostic]: Parsed diagnostics produced by the implementation.

        Raises:
            NotImplementedError: When the parser has not been implemented.
        """

        _protocol_not_implemented(f"{self.__class__.__qualname__}.parse")

    def __call__(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Forward to :meth:`parse` to support call-style parsers.

        Args:
            stdout: Lines emitted on standard output by the external tool.
            stderr: Lines emitted on standard error by the external tool.
            context: Tool execution context describing configuration and files.

        Returns:
            Sequence[RawDiagnostic | Diagnostic]: Parsed diagnostics produced by :meth:`parse`.

        """

        return self.parse(stdout, stderr, context=context)


@runtime_checkable
class ParserLike(Protocol):
    """Protocol describing callable objects capable of parsing diagnostics."""

    def parse(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Parse diagnostics emitted by a tool invocation.

        Args:
            stdout: Standard output produced by the tool.
            stderr: Standard error produced by the tool.
            context: Execution context passed to the parser.

        Returns:
            Sequence[RawDiagnostic | Diagnostic]: Parsed diagnostics produced by the implementation.

        Raises:
            NotImplementedError: When the parser-like object fails to implement parsing.
        """

        _protocol_not_implemented(f"{self.__class__.__qualname__}.parse")

    def __call__(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Return parsed diagnostics when invoked as a callable.

        Returns:
            Sequence[RawDiagnostic | Diagnostic]: Parsed diagnostics produced by :meth:`parse`.
        """

        return self.parse(stdout, stderr, context=context)


class ParserAdapter(Parser):
    """Adapter that wraps parser-like objects with the :class:`Parser` protocol."""

    __slots__ = ("_delegate",)

    def __init__(self, delegate: ParserLike) -> None:
        """Store the parser delegate used to handle diagnostic parsing.

        Args:
            delegate: Parser-like object that will perform diagnostic parsing.
        """

        self._delegate = delegate

    def parse(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Delegate parsing to the wrapped object and normalise the result.

        Args:
            stdout: Lines captured on standard output during execution.
            stderr: Lines captured on standard error during execution.
            context: Tool execution context passed to the delegate.

        Returns:
            Sequence[RawDiagnostic | Diagnostic]: Normalised diagnostic records returned by the delegate.
        """

        result = self._delegate.parse(stdout, stderr, context=context)
        return tuple(result)

    @property
    def delegate(self) -> ParserLike:
        """Return the wrapped parser delegate.

        Returns:
            ParserLike: Parser delegate provided at construction time.
        """

        return self._delegate


@runtime_checkable
class CommandBuilder(Protocol):
    """Build a command for execution based on the tool context."""

    @abstractmethod
    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Return command-line arguments for the tool invocation.

        Args:
            ctx: Tool execution context containing configuration and file selections.

        Returns:
            Sequence[str]: Command arguments to be executed.

        Raises:
            NotImplementedError: When the builder has not been implemented.
        """

        _protocol_not_implemented(f"{self.__class__.__qualname__}.build")

    def __call__(self, ctx: ToolContext) -> Sequence[str]:
        """Invoke :meth:`build` allowing builders to act as callables.

        Returns:
            Sequence[str]: Command arguments produced by :meth:`build`.
        """

        return self.build(ctx)


@runtime_checkable
class CommandBuilderLike(Protocol):
    """Protocol describing objects that can construct command arguments."""

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Return the command arguments for the provided context.

        Args:
            ctx: Tool execution context describing files and configuration.

        Returns:
            Sequence[str]: Command arguments emitted by the builder.
        """

        _protocol_not_implemented(f"{self.__class__.__qualname__}.build")

    def __call__(self, ctx: ToolContext) -> Sequence[str]:
        """Return command arguments when invoked as a callable.

        Returns:
            Sequence[str]: Command arguments produced by :meth:`build`.
        """

        return self.build(ctx)


@runtime_checkable
class InstallerCallable(Protocol):
    """Protocol implemented by installer callbacks."""

    def __call__(self, ctx: ToolContext) -> None:
        """Perform installation steps for the tool using ``ctx``.

        Args:
            ctx: Tool execution context made available to the installer.

        Returns:
            None
        """

        _protocol_not_implemented(f"{self.__class__.__qualname__}.__call__")

    def __repr__(self) -> str:
        """Return a debugging representation of the installer callable.

        Returns:
            str: Debug-friendly representation of the callable.
        """

        return f"InstallerCallable({self.__class__.__qualname__})"


@runtime_checkable
class InternalActionRunner(Protocol):
    """Protocol implemented by internal tool action runners."""

    def __call__(self, ctx: ToolContext) -> ToolOutcome:
        """Execute the action and return a :class:`ToolOutcome`.

        Args:
            ctx: Tool execution context describing configuration and target files.

        Returns:
            ToolOutcome: Result bundle describing the internal action.
        """

        _protocol_not_implemented(f"{self.__class__.__qualname__}.__call__")

    def __repr__(self) -> str:
        """Return a debugging representation of the action runner.

        Returns:
            str: Debug-friendly representation of the runner.
        """

        return f"InternalActionRunner({self.__class__.__qualname__})"


__all__ = [
    "CommandBuilder",
    "CommandBuilderLike",
    "InstallerCallable",
    "InternalActionRunner",
    "Parser",
    "ParserAdapter",
    "ParserLike",
]
