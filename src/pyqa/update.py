# SPDX-License-Identifier: MIT
"""Workspace discovery and dependency update orchestration."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence

from .constants import ALWAYS_EXCLUDE_DIRS
from .logging import fail, info, ok, warn


class WorkspaceKind(Enum):
    PYTHON = "python"
    PNPM = "pnpm"
    YARN = "yarn"
    NPM = "npm"
    GO = "go"
    RUST = "rust"

    @classmethod
    def from_str(cls, value: str) -> "WorkspaceKind":
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(value)


@dataclass(slots=True)
class Workspace:
    directory: Path
    kind: WorkspaceKind
    manifest: Path


@dataclass(slots=True)
class CommandSpec:
    args: tuple[str, ...]
    description: str | None = None
    requires: tuple[str, ...] = ()


@dataclass(slots=True)
class PlanCommand:
    spec: CommandSpec
    reason: str | None = None


@dataclass(slots=True)
class ExecutionDetail:
    command: CommandSpec
    status: str  # "ran", "skipped", "failed"
    message: str | None = None


@dataclass(slots=True)
class UpdatePlanItem:
    workspace: Workspace
    commands: list[PlanCommand]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UpdatePlan:
    items: list[UpdatePlanItem]


@dataclass(slots=True)
class UpdateResult:
    successes: list[Workspace] = field(default_factory=list)
    failures: list[tuple[Workspace, str]] = field(default_factory=list)
    skipped: list[Workspace] = field(default_factory=list)
    details: list[tuple[Workspace, list[ExecutionDetail]]] = field(default_factory=list)

    def register_success(self, workspace: Workspace, executions: list[ExecutionDetail]) -> None:
        self.successes.append(workspace)
        self.details.append((workspace, executions))

    def register_failure(self, workspace: Workspace, message: str, executions: list[ExecutionDetail]) -> None:
        self.failures.append((workspace, message))
        self.details.append((workspace, executions))

    def register_skip(self, workspace: Workspace, executions: list[ExecutionDetail]) -> None:
        self.skipped.append(workspace)
        self.details.append((workspace, executions))

    def exit_code(self) -> int:
        return 1 if self.failures else 0


class WorkspaceStrategy(Protocol):
    kind: WorkspaceKind

    def detect(self, directory: Path, filenames: set[str]) -> bool: ...

    def plan(self, workspace: Workspace) -> list[CommandSpec]: ...


class PythonStrategy:
    kind = WorkspaceKind.PYTHON

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        return "pyproject.toml" in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        commands: list[CommandSpec] = []
        if not (workspace.directory / ".venv").exists():
            commands.append(
                CommandSpec(
                    args=("uv", "venv"),
                    description="Create virtual env",
                    requires=("uv",),
                )
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
            )
        )
        return commands


class PnpmStrategy:
    kind = WorkspaceKind.PNPM

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        return "pnpm-lock.yaml" in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        return [
            CommandSpec(
                args=("pnpm", "up", "--latest"),
                description="Update pnpm workspace",
                requires=("pnpm",),
            )
        ]


class YarnStrategy:
    kind = WorkspaceKind.YARN

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        return "yarn.lock" in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        return [
            CommandSpec(
                args=("yarn", "upgrade", "--latest"),
                description="Upgrade yarn dependencies",
                requires=("yarn",),
            )
        ]


class NpmStrategy:
    kind = WorkspaceKind.NPM

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        return "package.json" in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        return [
            CommandSpec(
                args=("npm", "update"),
                description="Update npm dependencies",
                requires=("npm",),
            )
        ]


class GoStrategy:
    kind = WorkspaceKind.GO

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        return "go.mod" in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
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

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        return "Cargo.toml" in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        return [
            CommandSpec(
                args=("cargo", "update"),
                description="Update Cargo dependencies",
                requires=("cargo",),
            )
        ]


DEFAULT_STRATEGIES: tuple[WorkspaceStrategy, ...] = (
    PythonStrategy(),
    PnpmStrategy(),
    YarnStrategy(),
    NpmStrategy(),
    GoStrategy(),
    RustStrategy(),
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

    def discover(self, root: Path) -> list[Workspace]:
        root = root.resolve()
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
                    workspaces.append(Workspace(directory=directory, kind=strategy.kind, manifest=manifest))
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
        allowed = {WorkspaceKind.from_str(kind) for kind in enabled_managers} if enabled_managers else None
        items: list[UpdatePlanItem] = []
        for workspace in workspaces:
            if allowed and workspace.kind not in allowed:
                continue
            strategy = self._strategies.get(workspace.kind)
            if strategy is None:
                continue
            commands = strategy.plan(workspace)
            items.append(
                UpdatePlanItem(
                    workspace=workspace,
                    commands=[PlanCommand(spec=command) for command in commands],
                )
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
            workspace = item.workspace
            rel_path = _format_relative(workspace.directory, root)
            info(
                f"Updating {workspace.kind.value} workspace at {rel_path}",
                use_emoji=self._use_emoji,
            )
            if not item.commands:
                warn("No update strategy available", use_emoji=self._use_emoji)
                result.register_skip(workspace, [])
                continue
            executions: list[ExecutionDetail] = []
            for cmd in item.commands:
                spec = cmd.spec
                missing = [tool for tool in spec.requires if shutil.which(tool) is None]
                if missing:
                    message = f"missing {', '.join(missing)}"
                    warn(
                        f"Skipping command {' '.join(spec.args)} ({message})",
                        use_emoji=self._use_emoji,
                    )
                    executions.append(ExecutionDetail(command=spec, status="skipped", message=message))
                    continue
                if self._dry_run:
                    info(
                        f"DRY RUN: {' '.join(spec.args)}",
                        use_emoji=self._use_emoji,
                    )
                    executions.append(ExecutionDetail(command=spec, status="skipped", message="dry-run"))
                    continue
                cp = self._runner(spec.args, workspace.directory)
                if cp.returncode != 0:
                    message = f"Command '{' '.join(spec.args)}' failed with exit code {cp.returncode}"
                    fail(message, use_emoji=self._use_emoji)
                    executions.append(ExecutionDetail(command=spec, status="failed", message=message))
                    result.register_failure(workspace, f"{rel_path}: {message}", executions)
                    break
                executions.append(ExecutionDetail(command=spec, status="ran"))
            else:
                if self._dry_run:
                    result.register_skip(workspace, executions)
                elif all(detail.status == "skipped" for detail in executions):
                    warn(
                        f"No commands executed for {workspace.kind.value} workspace at {rel_path}",
                        use_emoji=self._use_emoji,
                    )
                    result.register_skip(workspace, executions)
                else:
                    ok("Workspace updated", use_emoji=self._use_emoji)
                    result.register_success(workspace, executions)
        return result


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


def _default_runner(args: Sequence[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=False, text=True)


def _format_relative(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return str(path)
    return str(relative) or "."


__all__ = [
    "Workspace",
    "WorkspaceKind",
    "WorkspaceDiscovery",
    "WorkspacePlanner",
    "WorkspaceUpdater",
    "UpdatePlan",
    "UpdatePlanItem",
    "UpdateResult",
    "CommandSpec",
    "PlanCommand",
    "ExecutionDetail",
    "DEFAULT_STRATEGIES",
    "ensure_lint_install",
]
