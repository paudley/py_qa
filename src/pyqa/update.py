# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Workspace discovery and dependency update orchestration."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any, Final, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import ALWAYS_EXCLUDE_DIRS, PY_QA_DIR_NAME
from .logging import fail, info, ok, warn
from .process_utils import run_command
from .workspace import is_py_qa_workspace

CommandRunner = Callable[[Sequence[str], Path | None], Any]


PYPROJECT_MANIFEST: Final[str] = "pyproject.toml"
PNPM_LOCKFILE: Final[str] = "pnpm-lock.yaml"
YARN_LOCKFILE: Final[str] = "yarn.lock"
NPM_MANIFEST: Final[str] = "package.json"
GO_MANIFEST: Final[str] = "go.mod"
CARGO_MANIFEST: Final[str] = "Cargo.toml"
SKIPPED_STATUS: Final = "skipped"


class WorkspaceKind(Enum):
    PYTHON = "python"
    PNPM = "pnpm"
    YARN = "yarn"
    NPM = "npm"
    GO = "go"
    RUST = "rust"

    @classmethod
    def from_str(cls, value: str) -> WorkspaceKind:
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(value)


class Workspace(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    directory: Path
    kind: WorkspaceKind
    manifest: Path


class CommandSpec(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    args: tuple[str, ...]
    description: str | None = None
    requires: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("args", mode="before")
    @classmethod
    def _coerce_args(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, tuple):
            return tuple(str(entry) for entry in value)
        if isinstance(value, (list, Sequence)):
            return tuple(str(entry) for entry in value)
        if isinstance(value, str):
            return (value,)
        raise TypeError("CommandSpec.args must be a sequence of strings")

    @field_validator("requires", mode="before")
    @classmethod
    def _coerce_requires(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, tuple):
            return tuple(str(entry) for entry in value)
        if isinstance(value, (list, Sequence, set)):
            return tuple(str(entry) for entry in value)
        if isinstance(value, str):
            return (value,)
        raise TypeError("CommandSpec.requires must be a sequence of strings")


class PlanCommand(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    spec: CommandSpec
    reason: str | None = None


class ExecutionDetail(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    command: CommandSpec
    status: Literal["ran", "skipped", "failed"]
    message: str | None = None


class UpdatePlanItem(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    workspace: Workspace
    commands: list[PlanCommand] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class UpdatePlan(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    items: list[UpdatePlanItem] = Field(default_factory=list)


class UpdateResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    successes: list[Workspace] = Field(default_factory=list)
    failures: list[tuple[Workspace, str]] = Field(default_factory=list)
    skipped: list[Workspace] = Field(default_factory=list)
    details: list[tuple[Workspace, list[ExecutionDetail]]] = Field(default_factory=list)

    def register_success(self, workspace: Workspace, executions: list[ExecutionDetail]) -> None:
        self.successes = [*self.successes, workspace]
        self.details = [*self.details, (workspace, executions)]

    def register_failure(
        self,
        workspace: Workspace,
        message: str,
        executions: list[ExecutionDetail],
    ) -> None:
        self.failures = [*self.failures, (workspace, message)]
        self.details = [*self.details, (workspace, executions)]

    def register_skip(self, workspace: Workspace, executions: list[ExecutionDetail]) -> None:
        self.skipped = [*self.skipped, workspace]
        self.details = [*self.details, (workspace, executions)]

    def exit_code(self) -> int:
        return 1 if self.failures else 0


class WorkspaceStrategy(Protocol):
    kind: WorkspaceKind

    def detect(self, directory: Path, filenames: set[str]) -> bool: ...

    def plan(self, workspace: Workspace) -> list[CommandSpec]: ...


class PythonStrategy:
    kind = WorkspaceKind.PYTHON

    def detect(self, _directory: Path, filenames: set[str]) -> bool:
        return PYPROJECT_MANIFEST in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        commands: list[CommandSpec] = []
        if not (workspace.directory / ".venv").exists():
            commands.append(
                CommandSpec(
                    args=("uv", "venv"),
                    description="Create virtual env",
                    requires=("uv",),
                ),
            )
        commands.append(
            CommandSpec(
                args=(
                    "uv",
                    "sync",
                    "-U",
                    "--all-extras",
                    "--all-groups",
                    "--managed-python",
                    "--link-mode=hardlink",
                    "--compile-bytecode",
                ),
                description="Synchronise Python dependencies",
                requires=("uv",),
            ),
        )
        return commands


class PnpmStrategy:
    kind = WorkspaceKind.PNPM

    def detect(self, _directory: Path, filenames: set[str]) -> bool:
        return PNPM_LOCKFILE in filenames

    def plan(self, _workspace: Workspace) -> list[CommandSpec]:
        return [
            CommandSpec(
                args=("pnpm", "up", "--latest"),
                description="Update pnpm workspace",
                requires=("pnpm",),
            ),
        ]


class YarnStrategy:
    kind = WorkspaceKind.YARN

    def detect(self, _directory: Path, filenames: set[str]) -> bool:
        return YARN_LOCKFILE in filenames

    def plan(self, _workspace: Workspace) -> list[CommandSpec]:
        return [
            CommandSpec(
                args=("yarn", "upgrade", "--latest"),
                description="Upgrade yarn dependencies",
                requires=("yarn",),
            ),
        ]


class NpmStrategy:
    kind = WorkspaceKind.NPM

    def detect(self, _directory: Path, filenames: set[str]) -> bool:
        return NPM_MANIFEST in filenames

    def plan(self, _workspace: Workspace) -> list[CommandSpec]:
        return [
            CommandSpec(
                args=("npm", "update"),
                description="Update npm dependencies",
                requires=("npm",),
            ),
        ]


class GoStrategy:
    kind = WorkspaceKind.GO

    def detect(self, _directory: Path, filenames: set[str]) -> bool:
        return GO_MANIFEST in filenames

    def plan(self, _workspace: Workspace) -> list[CommandSpec]:
        return [
            CommandSpec(
                args=("go", "get", "-u", "./..."),
                description="Update Go modules",
                requires=("go",),
            ),
            CommandSpec(args=("go", "mod", "tidy"), description="Tidy go.mod", requires=("go",)),
        ]


class RustStrategy:
    kind = WorkspaceKind.RUST

    def detect(self, _directory: Path, filenames: set[str]) -> bool:
        return CARGO_MANIFEST in filenames

    def plan(self, _workspace: Workspace) -> list[CommandSpec]:
        return [
            CommandSpec(
                args=("cargo", "update"),
                description="Update Cargo dependencies",
                requires=("cargo",),
            ),
        ]


DEFAULT_STRATEGIES: Final[tuple[WorkspaceStrategy, ...]] = (
    cast("WorkspaceStrategy", PythonStrategy()),
    cast("WorkspaceStrategy", PnpmStrategy()),
    cast("WorkspaceStrategy", YarnStrategy()),
    cast("WorkspaceStrategy", NpmStrategy()),
    cast("WorkspaceStrategy", GoStrategy()),
    cast("WorkspaceStrategy", RustStrategy()),
)


class WorkspaceDiscovery:
    """Discover workspaces using provided strategies."""

    def __init__(
        self,
        *,
        strategies: Iterable[WorkspaceStrategy] = DEFAULT_STRATEGIES,
        skip_patterns: Iterable[str] | None = None,
    ) -> None:
        self._strategies = list(strategies)
        self._skip_patterns = set(skip_patterns or [])
        self._skip_py_qa_dirs = False

    def discover(self, root: Path) -> list[Workspace]:
        root = root.resolve()
        self._skip_py_qa_dirs = not is_py_qa_workspace(root)
        workspaces: list[Workspace] = []
        for dirpath, dirnames, filenames in os.walk(root):
            directory = Path(dirpath)
            if self._should_skip(directory, root):
                dirnames[:] = []
                continue
            names = set(filenames)
            for strategy in self._strategies:
                if strategy.detect(directory, names):
                    manifest = _manifest_for(strategy.kind, directory)
                    workspaces.append(
                        Workspace(directory=directory, kind=strategy.kind, manifest=manifest),
                    )
                    break
        workspaces.sort(key=lambda ws: (ws.directory, ws.kind.value))
        return workspaces

    def _should_skip(self, directory: Path, root: Path) -> bool:
        try:
            relative = directory.relative_to(root)
        except ValueError:
            return True
        if any(part in ALWAYS_EXCLUDE_DIRS for part in relative.parts):
            return True
        if self._skip_py_qa_dirs and PY_QA_DIR_NAME in relative.parts:
            return True
        rel_str = str(relative)
        return any(pattern in rel_str for pattern in self._skip_patterns)


class WorkspacePlanner:
    """Create update plans for discovered workspaces."""

    def __init__(self, strategies: Iterable[WorkspaceStrategy]) -> None:
        self._strategies: Mapping[WorkspaceKind, WorkspaceStrategy] = {
            strategy.kind: strategy for strategy in strategies
        }

    def plan(
        self,
        workspaces: Iterable[Workspace],
        *,
        enabled_managers: Iterable[str] | None = None,
    ) -> UpdatePlan:
        allowed: set[WorkspaceKind] | None = (
            {WorkspaceKind.from_str(kind) for kind in enabled_managers}
            if enabled_managers
            else None
        )
        items: list[UpdatePlanItem] = []
        for workspace in workspaces:
            if allowed is not None and workspace.kind not in allowed:
                continue
            if (strategy := self._strategies.get(workspace.kind)) is None:
                continue
            commands = strategy.plan(workspace)
            items.append(
                UpdatePlanItem(
                    workspace=workspace,
                    commands=[PlanCommand(spec=command) for command in commands],
                ),
            )
        return UpdatePlan(items=items)


class WorkspaceUpdater:
    """Execute update plans for workspaces."""

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        dry_run: bool = False,
        use_emoji: bool = True,
    ) -> None:
        self._runner = runner or _default_runner
        self._dry_run = dry_run
        self._use_emoji = use_emoji

    def execute(self, plan: UpdatePlan, *, root: Path) -> UpdateResult:
        result = UpdateResult()
        for item in plan.items:
            self._process_plan_item(item=item, root=root, result=result)
        return result

    def _process_plan_item(self, *, item: UpdatePlanItem, root: Path, result: UpdateResult) -> None:
        workspace = item.workspace
        rel_path = _format_relative(workspace.directory, root)
        info(
            f"Updating {workspace.kind.value} workspace at {rel_path}",
            use_emoji=self._use_emoji,
        )
        if not item.commands:
            warn("No update strategy available", use_emoji=self._use_emoji)
            result.register_skip(workspace, [])
            return

        executions: list[ExecutionDetail] = []
        for plan_command in item.commands:
            detail, failure = self._execute_command(
                workspace=workspace,
                spec=plan_command.spec,
                rel_path=rel_path,
            )
            executions.append(detail)
            if failure is not None:
                result.register_failure(workspace, failure, executions)
                return

        if all(detail.status == SKIPPED_STATUS for detail in executions):
            warn(
                f"No commands executed for {workspace.kind.value} workspace at {rel_path}",
                use_emoji=self._use_emoji,
            )
            result.register_skip(workspace, executions)
            return

        if self._dry_run:
            result.register_skip(workspace, executions)
            return

        ok("Workspace updated", use_emoji=self._use_emoji)
        result.register_success(workspace, executions)

    def _execute_command(
        self,
        *,
        workspace: Workspace,
        spec: CommandSpec,
        rel_path: str,
    ) -> tuple[ExecutionDetail, str | None]:
        if missing := [tool for tool in spec.requires if shutil.which(tool) is None]:
            message = f"missing {', '.join(missing)}"
            warn(
                f"Skipping command {' '.join(spec.args)} ({message})",
                use_emoji=self._use_emoji,
            )
            detail = ExecutionDetail(command=spec, status=SKIPPED_STATUS, message=message)
            return detail, None

        if self._dry_run:
            info(
                f"DRY RUN: {' '.join(spec.args)}",
                use_emoji=self._use_emoji,
            )
            detail = ExecutionDetail(command=spec, status=SKIPPED_STATUS, message="dry-run")
            return detail, None

        completed = self._runner(spec.args, workspace.directory)
        if completed.returncode != 0:
            message = (
                f"Command '{' '.join(spec.args)}' failed with exit code {completed.returncode}"
            )
            fail(message, use_emoji=self._use_emoji)
            detail = ExecutionDetail(command=spec, status="failed", message=message)
            summary = f"{rel_path}: {message}"
            return detail, summary

        detail = ExecutionDetail(command=spec, status="ran")
        return detail, None


def ensure_lint_install(root: Path, runner: CommandRunner, *, dry_run: bool) -> None:
    lint_shim = root / "py-qa" / "lint"
    if not lint_shim.exists():
        return
    command = (str(lint_shim), "install")
    info("Ensuring py-qa lint dependencies are installed", use_emoji=True)
    if dry_run:
        info(f"DRY RUN: {' '.join(command)}", use_emoji=True)
        return
    cp = runner(command, root)
    if cp.returncode != 0:
        warn(
            f"py-qa lint install failed with exit code {cp.returncode}",
            use_emoji=True,
        )


def _manifest_for(kind: WorkspaceKind, directory: Path) -> Path:
    mapping = {
        WorkspaceKind.PYTHON: "pyproject.toml",
        WorkspaceKind.PNPM: "pnpm-lock.yaml",
        WorkspaceKind.YARN: "yarn.lock",
        WorkspaceKind.NPM: "package.json",
        WorkspaceKind.GO: "go.mod",
        WorkspaceKind.RUST: "Cargo.toml",
    }
    name = mapping.get(kind)
    return directory / name if name else directory


def _default_runner(args: Sequence[str], cwd: Path | None) -> Any:
    return run_command(args, cwd=cwd, check=False)


def _format_relative(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return str(path)
    return str(relative) or "."


__all__ = [
    "DEFAULT_STRATEGIES",
    "CommandRunner",
    "CommandSpec",
    "ExecutionDetail",
    "PlanCommand",
    "UpdatePlan",
    "UpdatePlanItem",
    "UpdateResult",
    "Workspace",
    "WorkspaceDiscovery",
    "WorkspaceKind",
    "WorkspacePlanner",
    "WorkspaceUpdater",
    "ensure_lint_install",
]
