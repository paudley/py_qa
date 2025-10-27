# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Data models and protocols supporting the update installer."""

from __future__ import annotations

from collections.abc import Sequence, Set
from enum import Enum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExecutionStatus(str, Enum):
    """Execution lifecycle markers emitted for each plan command."""

    RAN = "ran"
    SKIPPED = "skipped"
    FAILED = "failed"


SKIPPED_STATUS = ExecutionStatus.SKIPPED


class WorkspaceKind(Enum):
    """Enumeration describing supported workspace categories."""

    PYTHON = "python"
    PNPM = "pnpm"
    YARN = "yarn"
    NPM = "npm"
    GO = "go"
    RUST = "rust"

    @classmethod
    def from_str(cls, value: str) -> WorkspaceKind:
        """Return the matching :class:`WorkspaceKind` for ``value``.

        Args:
            value: Normalised string representation of a workspace kind.

        Returns:
            WorkspaceKind: Enum instance associated with *value*.

        Raises:
            ValueError: If *value* does not represent a known workspace kind.
        """

        try:
            return cls(value)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(value) from exc


class Workspace(BaseModel):
    """Description of a detected workspace slated for dependency updates."""

    model_config = ConfigDict(validate_assignment=True)

    directory: Path
    kind: WorkspaceKind
    manifest: Path

    def __str__(self) -> str:
        """Return a concise string representation of the workspace.

        Returns:
            str: ``"<kind>:<directory>"`` string describing the workspace.
        """

        return f"{self.kind.value}:{self.directory}"

    def manifest_exists(self) -> bool:
        """Return ``True`` when the workspace manifest exists on disk.

        Returns:
            bool: ``True`` when :attr:`manifest` points to an existing file.
        """

        return self.manifest.exists()


class CommandSpec(BaseModel):
    """Specification describing an update command and its prerequisites."""

    model_config = ConfigDict(validate_assignment=True)

    args: tuple[str, ...]
    description: str | None = None
    requires: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("args", mode="before")
    @classmethod
    def _coerce_args(cls, value: Sequence[str] | str) -> tuple[str, ...]:
        """Return ``value`` coerced into an immutable tuple of argument strings.

        Args:
            value: Sequence or scalar representing command arguments.

        Returns:
            tuple[str, ...]: Normalised command arguments.

        Raises:
            TypeError: If *value* cannot be coerced into a sequence of strings.
        """

        if isinstance(value, str):
            return (value,)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return tuple(str(entry) for entry in value)
        raise TypeError("CommandSpec.args must be a sequence of strings")

    @field_validator("requires", mode="before")
    @classmethod
    def _coerce_requires(cls, value: Sequence[str] | Set[str] | str | None) -> tuple[str, ...]:
        """Return ``value`` coerced into an immutable tuple of requirement names.

        Args:
            value: Sequence or scalar describing prerequisite tool names.

        Returns:
            tuple[str, ...]: Normalised prerequisite identifiers.

        Raises:
            TypeError: If *value* cannot be coerced into a sequence of strings.
        """

        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, set):
            return tuple(str(entry) for entry in value)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return tuple(str(entry) for entry in value)
        raise TypeError("CommandSpec.requires must be a sequence of strings")

    def render(self) -> str:
        """Return the command arguments joined into a shell-style string.

        Returns:
            str: Arguments concatenated with single spaces for logging.
        """

        return " ".join(self.args)

    def required_tools(self) -> tuple[str, ...]:
        """Return the external tools required prior to executing the command.

        Returns:
            tuple[str, ...]: Names of executables that must be available on ``PATH``.
        """

        return self.requires


class PlanCommand(BaseModel):
    """Wrapper pairing a :class:`CommandSpec` with optional rationale."""

    model_config = ConfigDict(validate_assignment=True)

    spec: CommandSpec
    reason: str | None = None

    def describe(self) -> str:
        """Return the human-readable description for the plan command.

        Returns:
            str: Explicit rationale when available, otherwise the command string.
        """

        return self.reason or self.spec.description or self.spec.render()

    def has_reason(self) -> bool:
        """Return ``True`` when the plan command includes a detailed rationale.

        Returns:
            bool: ``True`` when :attr:`reason` is non-empty.
        """

        return bool(self.reason)


class ExecutionDetail(BaseModel):
    """Outcome captured for a command executed (or skipped) during updates."""

    model_config = ConfigDict(validate_assignment=True)

    command: CommandSpec
    status: ExecutionStatus
    message: str | None = None

    def is_success(self) -> bool:
        """Return ``True`` when the command executed successfully.

        Returns:
            bool: ``True`` when :attr:`status` equals :data:`ExecutionStatus.RAN`.
        """

        return self.status is ExecutionStatus.RAN

    def is_skipped(self) -> bool:
        """Return ``True`` when the command did not execute due to gating conditions.

        Returns:
            bool: ``True`` when the command was skipped (dry-run or missing tools).
        """

        return self.status is SKIPPED_STATUS


class UpdatePlanItem(BaseModel):
    """Plan representation for updating a single workspace."""

    model_config = ConfigDict(validate_assignment=True)

    workspace: Workspace
    commands: list[PlanCommand] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def add_warning(self, message: str) -> None:
        """Append a warning to the plan item.

        Args:
            message: Warning message to record.
        """

        self.warnings = [*self.warnings, message]

    def has_commands(self) -> bool:
        """Return ``True`` when the plan item contains commands to execute.

        Returns:
            bool: ``True`` when :attr:`commands` is non-empty.
        """

        return bool(self.commands)


class UpdatePlan(BaseModel):
    """Aggregated plan covering all workspaces slated for updates."""

    model_config = ConfigDict(validate_assignment=True)

    items: list[UpdatePlanItem] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """Return ``True`` when the plan does not contain any workspaces.

        Returns:
            bool: ``True`` when :attr:`items` is empty.
        """

        return not self.items

    def total_commands(self) -> int:
        """Return the total number of commands scheduled across all plan items.

        Returns:
            int: Sum of commands contained within every :class:`UpdatePlanItem`.
        """

        return sum(len(item.commands) for item in self.items)


class UpdateResult(BaseModel):
    """Execution results captured while applying an :class:`UpdatePlan`."""

    model_config = ConfigDict(validate_assignment=True)

    successes: list[Workspace] = Field(default_factory=list)
    failures: list[tuple[Workspace, str]] = Field(default_factory=list)
    skipped: list[Workspace] = Field(default_factory=list)
    details: list[tuple[Workspace, list[ExecutionDetail]]] = Field(default_factory=list)

    def register_success(self, workspace: Workspace, executions: list[ExecutionDetail]) -> None:
        """Record a successfully updated workspace.

        Args:
            workspace: Workspace that completed all commands without failure.
            executions: Execution details describing the commands that ran.
        """

        self.successes = [*self.successes, workspace]
        self.details = [*self.details, (workspace, executions)]

    def register_failure(
        self,
        workspace: Workspace,
        message: str,
        executions: list[ExecutionDetail],
    ) -> None:
        """Record a workspace failure and persist its execution details.

        Args:
            workspace: Workspace that encountered an error.
            message: Human-readable summary for the failure.
            executions: Execution details collected up to the failure.
        """

        self.failures = [*self.failures, (workspace, message)]
        self.details = [*self.details, (workspace, executions)]

    def register_skip(self, workspace: Workspace, executions: list[ExecutionDetail]) -> None:
        """Record a skipped workspace (dry-run or unsupported).

        Args:
            workspace: Workspace that did not run any update commands.
            executions: Execution details collected for the workspace.
        """

        self.skipped = [*self.skipped, workspace]
        self.details = [*self.details, (workspace, executions)]

    def exit_code(self) -> int:
        """Return ``1`` when failures were observed, otherwise ``0``.

        Returns:
            int: ``1`` if any workspace failed, otherwise ``0``.
        """

        return 1 if self.failures else 0


class WorkspaceStrategy(Protocol):
    """Abstraction implemented by per-ecosystem update strategies."""

    kind: WorkspaceKind

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        """Return ``True`` when ``directory`` belongs to this strategy.

        Args:
            directory: Directory being evaluated.
            filenames: Filenames contained within ``directory``.

        Returns:
            bool: ``True`` when the strategy can manage the workspace, ``False`` otherwise.
        """

        raise NotImplementedError("WorkspaceStrategy.detect must be implemented")

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        """Return the commands required to update ``workspace``.

        Args:
            workspace: Workspace to update.

        Returns:
            list[CommandSpec]: Commands that update the workspace or an empty list
            when no actions are required.
        """

        raise NotImplementedError("WorkspaceStrategy.plan must be implemented")


__all__ = [
    "CommandSpec",
    "ExecutionDetail",
    "ExecutionStatus",
    "PlanCommand",
    "SKIPPED_STATUS",
    "UpdatePlan",
    "UpdatePlanItem",
    "UpdateResult",
    "Workspace",
    "WorkspaceKind",
    "WorkspaceStrategy",
]
