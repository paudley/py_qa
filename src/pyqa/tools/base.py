"""Definitions for lint tools and their actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping, Protocol, Sequence

from ..config import Config
from ..models import Diagnostic, OutputFilter, RawDiagnostic


@dataclass(slots=True)
class ToolContext:
    """Runtime context made available when resolving tool commands."""

    cfg: Config
    root: Path
    files: Sequence[Path]


class Parser(Protocol):
    """Protocol implemented by output parsers."""

    def parse(
        self,
        stdout: str,
        stderr: str,
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic | Diagnostic]:
        """Convert raw tool output into diagnostics or raw diagnostics."""
        raise NotImplementedError


class CommandBuilder(Protocol):
    """Build a command for execution based on the tool context."""

    def build(self, ctx: ToolContext) -> Sequence[str]: ...


@dataclass(slots=True)
class DeferredCommand:
    """Simple command builder that returns a fixed command list."""

    args: Sequence[str]

    def build(
        self, ctx: ToolContext
    ) -> Sequence[str]:  # noqa: D401 - simple delegation
        del ctx
        return tuple(self.args)


@dataclass(slots=True)
class ToolAction:
    """Single executable action belonging to a tool (e.g. lint, fix)."""

    name: str
    command: CommandBuilder
    is_fix: bool = False
    append_files: bool = True
    filter_patterns: Sequence[str] = field(default_factory=tuple)
    ignore_exit: bool = False
    description: str = ""
    timeout_s: float | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    parser: Parser | None = None

    def build_command(self, ctx: ToolContext) -> list[str]:
        cmd = list(self.command.build(ctx))
        if self.append_files and ctx.files:
            cmd.extend(str(path) for path in ctx.files)
        return cmd

    def filter_stdout(
        self, text: str, extra_patterns: Sequence[str] | None = None
    ) -> str:
        patterns = list(self.filter_patterns)
        if extra_patterns:
            patterns.extend(extra_patterns)
        return OutputFilter(patterns).apply(text)

    def filter_stderr(
        self, text: str, extra_patterns: Sequence[str] | None = None
    ) -> str:
        patterns = list(self.filter_patterns)
        if extra_patterns:
            patterns.extend(extra_patterns)
        return OutputFilter(patterns).apply(text)


@dataclass(slots=True)
class Tool:
    """Description of a lint tool composed of multiple actions."""

    name: str
    actions: Sequence[ToolAction]
    languages: Sequence[str] = field(default_factory=tuple)
    file_extensions: Sequence[str] = field(default_factory=tuple)
    config_files: Sequence[str] = field(default_factory=tuple)
    description: str = ""
    auto_install: bool = False
    default_enabled: bool = True
    runtime: Literal["python", "npm", "binary"] = "python"
    package: str | None = None
    min_version: str | None = None
    prefer_local: bool = False
    version_command: Sequence[str] | None = None

    def is_applicable(
        self, *, language: str | None = None, files: Sequence[Path] | None = None
    ) -> bool:
        if language and self.languages and language not in self.languages:
            return False
        if files:
            allowed = set(ext.lower() for ext in self.file_extensions)
            if allowed and not any(path.suffix.lower() in allowed for path in files):
                return False
        return True
