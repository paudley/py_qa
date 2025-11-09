# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Reusable tool protocol definitions and adapters."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pyqa.core.models import Diagnostic, RawDiagnostic, ToolOutcome
from pyqa.interfaces.tools import ToolContext


@runtime_checkable
class ParserImplementation(Protocol):
    """Protocol describing the minimal parse surface accepted by tool actions."""

    @abstractmethod
    def parse(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Parse output streams produced by an external tool.

        Implementations must convert the provided ``stdout``/``stderr`` sequences
        into diagnostics suitable for downstream processing.

        Args:
            stdout: Lines emitted on standard output by the external tool.
            stderr: Lines emitted on standard error by the external tool.
            context: Tool execution context describing configuration and files.

        Returns:
            Sequence[RawDiagnostic | Diagnostic]: Parsed diagnostics derived from the tool output streams.

        Raises:
            NotImplementedError: When the parser has not been implemented.
        """

        raise NotImplementedError("Parser.parse must be implemented")


@runtime_checkable
class Parser(ParserImplementation, Protocol):
    """Protocol implemented by output parsers."""

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
            Sequence[RawDiagnostic | Diagnostic]: Parsed diagnostics derived from the tool output streams.

        Raises:
            NotImplementedError: When the parser-like object fails to implement parsing.
        """

        raise NotImplementedError("ParserLike.parse must be implemented")

    def __call__(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Return parsed diagnostics when invoked as a callable.

        Args:
            stdout: Lines emitted on standard output by the external tool.
            stderr: Lines emitted on standard error by the external tool.
            context: Tool execution context describing configuration and files.

        Returns:
            Sequence[RawDiagnostic | Diagnostic]: Parsed diagnostics produced by :meth:`parse`.
        """

        return self.parse(stdout, stderr, context=context)


@runtime_checkable
class ParserContract(Protocol):
    """Protocol describing objects exposing a parse method."""

    def __call__(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Return parsed diagnostics when invoked as a callable."""
        ...

    def parse(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Parse diagnostics emitted by a tool invocation.

        Args:
            stdout: Lines emitted on standard output by the external tool.
            stderr: Lines emitted on standard error by the external tool.
            context: Tool execution context describing configuration and files.

        Returns:
            Sequence[RawDiagnostic | Diagnostic]: Parsed diagnostics derived from the tool output streams.
        """

        raise NotImplementedError("ParserContract.parse must be implemented")

    def __call__(
        self,
        stdout: Sequence[str],
        stderr: Sequence[str],
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Return parsed diagnostics when invoked as a callable.

        Args:
            stdout: Lines emitted on standard output by the external tool.
            stderr: Lines emitted on standard error by the external tool.
            context: Tool execution context describing configuration and files.

        Returns:
            Sequence[RawDiagnostic | Diagnostic]: Parsed diagnostics produced by :meth:`parse`.
        """

        return self.parse(stdout, stderr, context=context)


@runtime_checkable
class CommandBuilder(Protocol):
    """Build a command for execution based on the tool context."""

    @abstractmethod
    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Return command-line arguments for the tool invocation.

        Args:
            ctx: Tool execution context containing configuration and file selections.

        Returns:
            Sequence[str]: Command arguments produced by the builder.

        Raises:
            NotImplementedError: When the builder has not been implemented.
        """

        raise NotImplementedError("CommandBuilder.build must be implemented")

    def __call__(self, ctx: ToolContext) -> Sequence[str]:
        """Invoke :meth:`build` allowing builders to act as callables.

        Args:
            ctx: Tool execution context containing configuration and file selections.

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

        raise NotImplementedError("CommandBuilderLike.build must be implemented")

    def __call__(self, ctx: ToolContext) -> Sequence[str]:
        """Return command arguments when invoked as a callable.

        Args:
            ctx: Tool execution context describing files and configuration.

        Returns:
            Sequence[str]: Command arguments produced by :meth:`build`.
        """

        return self.build(ctx)


@runtime_checkable
class CommandBuilderContract(Protocol):
    """Protocol describing objects that expose a build method."""

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Return command arguments for the provided context.

        Args:
            ctx: Tool execution context containing configuration and file selections.

        Returns:
            Sequence[str]: Command arguments produced by the builder.
        """

        raise NotImplementedError("CommandBuilderContract.build must be implemented")

    def __call__(self, ctx: ToolContext) -> Sequence[str]:
        """Invoke :meth:`build` allowing builders to act as callables.

        Args:
            ctx: Tool execution context containing configuration and file selections.

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
            None: Installers do not return a value.
        """

        raise NotImplementedError("InstallerCallable.__call__ must be implemented")

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
            ToolOutcome: Result bundle describing the internal action run.
        """

        raise NotImplementedError("InternalActionRunner.__call__ must be implemented")

    def __repr__(self) -> str:
        """Return a debugging representation of the action runner.

        Returns:
            str: Debug-friendly representation of the runner.
        """

        return f"InternalActionRunner({self.__class__.__qualname__})"


__all__ = [
    "CommandBuilder",
    "CommandBuilderLike",
    "CommandBuilderContract",
    "InstallerCallable",
    "InternalActionRunner",
    "Parser",
    "ParserImplementation",
    "ParserLike",
    "ParserContract",
    "ToolContext",
]
