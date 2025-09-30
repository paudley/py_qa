# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Workspace discovery and dependency update orchestration."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import Enum
from pathlib import Path
from subprocess import CompletedProcess
from typing import Final, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import ALWAYS_EXCLUDE_DIRS, PY_QA_DIR_NAME
from .logging import fail, info, ok, warn
from .process_utils import run_command
from .workspace import is_py_qa_workspace

CommandRunner = Callable[[Sequence[str], Path | None], CompletedProcess[str]]


PYPROJECT_MANIFEST: Final[str] = "pyproject.toml"
PNPM_LOCKFILE: Final[str] = "pnpm-lock.yaml"
YARN_LOCKFILE: Final[str] = "yarn.lock"
NPM_MANIFEST: Final[str] = "package.json"
GO_MANIFEST: Final[str] = "go.mod"
CARGO_MANIFEST: Final[str] = "Cargo.toml"


class ExecutionStatus(str, Enum):
    """Execution lifecycle markers emitted for each plan command."""

    RAN = "ran"
    SKIPPED = "skipped"
    FAILED = "failed"


SKIPPED_STATUS: Final[ExecutionStatus] = ExecutionStatus.SKIPPED


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
        """Return a concise string representation of the workspace."""

        return f"{self.kind.value}:{self.directory}"


class CommandSpec(BaseModel):
    """Specification describing an update command and its prerequisites."""

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
    """Wrapper pairing a :class:`CommandSpec` with optional rationale."""

    model_config = ConfigDict(validate_assignment=True)

    spec: CommandSpec
    reason: str | None = None


class ExecutionDetail(BaseModel):
    """Outcome captured for a command executed (or skipped) during updates."""

    model_config = ConfigDict(validate_assignment=True)

    command: CommandSpec
    status: ExecutionStatus
    message: str | None = None


class UpdatePlanItem(BaseModel):
    """Plan representation for updating a single workspace."""

    model_config = ConfigDict(validate_assignment=True)

    workspace: Workspace
    commands: list[PlanCommand] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class UpdatePlan(BaseModel):
    """Aggregated plan covering all workspaces slated for updates."""

    model_config = ConfigDict(validate_assignment=True)

    items: list[UpdatePlanItem] = Field(default_factory=list)


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
            bool: ``True`` if the strategy can manage the workspace.
        """

        ...

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        """Return the commands required to update ``workspace``.

        Args:
            workspace: Workspace to update.

        Returns:
            list[CommandSpec]: Commands that perform the update.
        """

        ...


class PythonStrategy:
    """Update strategy for Python projects managed through uv."""

    kind = WorkspaceKind.PYTHON

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        """Return ``True`` when a ``pyproject.toml`` manifest exists.

        Args:
            directory: Candidate directory being inspected.
            filenames: Filenames contained in the directory.

        Returns:
            bool: ``True`` if the strategy should manage the directory.
        """

        manifest_path = directory / PYPROJECT_MANIFEST
        return manifest_path.exists() or PYPROJECT_MANIFEST in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        """Return uv commands that synchronise Python dependencies.

        Args:
            workspace: Workspace whose dependencies should be updated.

        Returns:
            list[CommandSpec]: Ordered command specifications for uv.

        """

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
    """Update strategy for Node.js workspaces managed by pnpm."""

    kind = WorkspaceKind.PNPM

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        """Return ``True`` when a ``pnpm-lock.yaml`` file is present.

        Args:
            directory: Candidate directory being inspected.
            filenames: Filenames contained in the directory.

        Returns:
            bool: ``True`` if this strategy should handle the directory.
        """

        manifest_path = directory / PNPM_LOCKFILE
        return manifest_path.exists() or PNPM_LOCKFILE in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        """Return commands that upgrade the pnpm workspace to latest versions.

        Args:
            workspace: Workspace whose dependencies should be updated.

        Returns:
            list[CommandSpec]: Command specifications to run with pnpm.
        """

        label = workspace.directory.name or str(workspace.directory)
        return [
            CommandSpec(
                args=("pnpm", "up", "--latest"),
                description=f"Update pnpm workspace {label}",
                requires=("pnpm",),
            ),
        ]


class YarnStrategy:
    """Update strategy for Yarn-based JavaScript workspaces."""

    kind = WorkspaceKind.YARN

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        """Return ``True`` when a ``yarn.lock`` manifest exists.

        Args:
            directory: Candidate directory being inspected.
            filenames: Filenames contained in the directory.

        Returns:
            bool: ``True`` if this strategy should manage the directory.
        """

        manifest_path = directory / YARN_LOCKFILE
        return manifest_path.exists() or YARN_LOCKFILE in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        """Return commands that upgrade Yarn dependencies.

        Args:
            workspace: Workspace whose dependencies should be updated.

        Returns:
            list[CommandSpec]: Command specifications to execute via Yarn.
        """

        label = workspace.directory.name or str(workspace.directory)
        return [
            CommandSpec(
                args=("yarn", "upgrade", "--latest"),
                description=f"Upgrade yarn dependencies in {label}",
                requires=("yarn",),
            ),
        ]


class NpmStrategy:
    """Update strategy for npm-managed projects."""

    kind = WorkspaceKind.NPM

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        """Return ``True`` when ``package.json`` is present.

        Args:
            directory: Candidate directory being inspected.
            filenames: Filenames contained in the directory.

        Returns:
            bool: ``True`` if this strategy should handle the directory.
        """

        manifest_path = directory / NPM_MANIFEST
        return manifest_path.exists() or NPM_MANIFEST in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        """Return commands that update npm-managed dependencies.

        Args:
            workspace: Workspace whose dependencies should be updated.

        Returns:
            list[CommandSpec]: Command specifications to execute via npm.
        """

        label = workspace.directory.name or str(workspace.directory)
        return [
            CommandSpec(
                args=("npm", "update"),
                description=f"Update npm dependencies in {label}",
                requires=("npm",),
            ),
        ]


class GoStrategy:
    """Update strategy for Go modules."""

    kind = WorkspaceKind.GO

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        """Return ``True`` when ``go.mod`` is present.

        Args:
            directory: Candidate directory being inspected.
            filenames: Filenames contained in the directory.

        Returns:
            bool: ``True`` if this strategy should handle the directory.
        """

        manifest_path = directory / GO_MANIFEST
        return manifest_path.exists() or GO_MANIFEST in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        """Return commands that upgrade Go module dependencies.

        Args:
            workspace: Workspace whose dependencies should be updated.

        Returns:
            list[CommandSpec]: Command specifications to execute via the Go toolchain.
        """

        label = workspace.directory.name or str(workspace.directory)
        return [
            CommandSpec(
                args=("go", "get", "-u", "./..."),
                description=f"Update Go modules in {label}",
                requires=("go",),
            ),
            CommandSpec(
                args=("go", "mod", "tidy"),
                description=f"Tidy go.mod for {label}",
                requires=("go",),
            ),
        ]


class RustStrategy:
    """Update strategy for Cargo-based Rust projects."""

    kind = WorkspaceKind.RUST

    def detect(self, directory: Path, filenames: set[str]) -> bool:
        """Return ``True`` when ``Cargo.toml`` is present.

        Args:
            directory: Candidate directory being inspected.
            filenames: Filenames contained in the directory.

        Returns:
            bool: ``True`` if this strategy should handle the directory.
        """

        manifest_path = directory / CARGO_MANIFEST
        return manifest_path.exists() or CARGO_MANIFEST in filenames

    def plan(self, workspace: Workspace) -> list[CommandSpec]:
        """Return commands that update Cargo dependencies.

        Args:
            workspace: Workspace whose dependencies should be updated.

        Returns:
            list[CommandSpec]: Command specifications to execute via Cargo.
        """

        label = workspace.directory.name or str(workspace.directory)
        return [
            CommandSpec(
                args=("cargo", "update"),
                description=f"Update Cargo dependencies in {label}",
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
    """Discover workspaces using the supplied :class:`WorkspaceStrategy` instances."""

    def __init__(
        self,
        *,
        strategies: Iterable[WorkspaceStrategy] = DEFAULT_STRATEGIES,
        skip_patterns: Iterable[str] | None = None,
    ) -> None:
        """Initialise the discovery engine.

        Args:
            strategies: Strategies to evaluate for each directory visited.
            skip_patterns: Optional collection of substrings that, when present
                in a relative path, cause the directory to be skipped entirely.

        """

        self._strategies = list(strategies)
        self._skip_patterns = set(skip_patterns or [])
        self._skip_py_qa_dirs = False

    def available_kinds(self) -> tuple[WorkspaceKind, ...]:
        """Return the set of workspace kinds handled by this discovery.

        Returns:
            tuple[WorkspaceKind, ...]: Supported workspace kinds.

        """

        return tuple(strategy.kind for strategy in self._strategies)

    def discover(self, root: Path) -> list[Workspace]:
        """Return all supported workspaces rooted beneath ``root``.

        Args:
            root: Filesystem directory that acts as the search boundary.

        Returns:
            list[Workspace]: Sorted collection of detected workspaces.

        """

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
        """Return ``True`` when ``directory`` should be ignored.

        Args:
            directory: Directory currently being evaluated.
            root: Project root acting as the traversal boundary.

        Returns:
            bool: ``True`` when the directory should not be inspected further.

        """

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
        """Initialise the planner with the set of available strategies."""

        self._strategies: Mapping[WorkspaceKind, WorkspaceStrategy] = {
            strategy.kind: strategy for strategy in strategies
        }

    def supported_kinds(self) -> tuple[WorkspaceKind, ...]:
        """Return the workspace kinds understood by the planner."""

        return tuple(self._strategies.keys())

    def plan(
        self,
        workspaces: Iterable[Workspace],
        *,
        enabled_managers: Iterable[str] | None = None,
    ) -> UpdatePlan:
        """Build an :class:`UpdatePlan` for the supplied workspaces.

        Args:
            workspaces: Discovered workspaces to include in the plan.
            enabled_managers: Optional subset of workspace kinds to execute.

        Returns:
            UpdatePlan: Structured plan describing commands per workspace.

        """

        allowed: set[WorkspaceKind] | None = None
        if enabled_managers is not None:
            allowed = {WorkspaceKind.from_str(kind) for kind in enabled_managers}
        items: list[UpdatePlanItem] = []
        for workspace in workspaces:
            if allowed is not None and workspace.kind not in allowed:
                continue
            strategy = self._strategies.get(workspace.kind)
            if strategy is None:
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
        """Initialise the updater.

        Args:
            runner: Callable used to execute shell commands.
            dry_run: When ``True`` commands are logged but not executed.
            use_emoji: When ``True`` rich logging includes emoji markers.
        """

        self._runner = runner or _default_runner
        self._dry_run = dry_run
        self._use_emoji = use_emoji

    def is_dry_run(self) -> bool:
        """Return ``True`` when the updater is operating in dry-run mode.

        Returns:
            bool: ``True`` if commands are skipped rather than executed.
        """

        return self._dry_run

    def execute(self, plan: UpdatePlan, *, root: Path) -> UpdateResult:
        """Execute ``plan`` relative to ``root`` and return the aggregated result.

        Args:
            plan: Plan containing workspaces and their commands.
            root: Project root used for relative path reporting.

        Returns:
            UpdateResult: Collected execution summary.
        """

        result = UpdateResult()
        for item in plan.items:
            self._process_plan_item(item=item, root=root, result=result)
        return result

    def _process_plan_item(
        self,
        *,
        item: UpdatePlanItem,
        root: Path,
        result: UpdateResult,
    ) -> None:
        """Execute the commands for a single plan item and record outcomes.

        Args:
            item: Plan item currently being executed.
            root: Project root used for relative path presentation.
            result: Aggregate result recorder tracking successes/failures.
        """

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
        """Execute a single command returning detail metadata and failure summary.

        Args:
            workspace: Workspace the command operates on.
            spec: Command specification to execute.
            rel_path: Workspace path relative to the project root for logging.

        Returns:
            tuple[ExecutionDetail, str | None]: Execution detail paired with an
            optional failure summary suitable for user-facing messages.
        """

        missing_tools = [tool for tool in spec.requires if shutil.which(tool) is None]
        if missing_tools:
            message = f"missing {', '.join(missing_tools)}"
            warn(
                f"Skipping command {' '.join(spec.args)} ({message})",
                use_emoji=self._use_emoji,
            )
            detail = ExecutionDetail(
                command=spec,
                status=SKIPPED_STATUS,
                message=message,
            )
            return detail, None

        if self._dry_run:
            info(
                f"DRY RUN: {' '.join(spec.args)}",
                use_emoji=self._use_emoji,
            )
            detail = ExecutionDetail(
                command=spec,
                status=SKIPPED_STATUS,
                message="dry-run",
            )
            return detail, None

        completed = self._runner(spec.args, workspace.directory)
        if completed.returncode != 0:
            message = f"Command '{' '.join(spec.args)}' failed with exit code {completed.returncode}"
            fail(message, use_emoji=self._use_emoji)
            detail = ExecutionDetail(
                command=spec,
                status=ExecutionStatus.FAILED,
                message=message,
            )
            summary = f"{rel_path}: {message}"
            return detail, summary

        detail = ExecutionDetail(command=spec, status=ExecutionStatus.RAN)
        return detail, None


def ensure_lint_install(root: Path, runner: CommandRunner, *, dry_run: bool) -> None:
    """Ensure the mono-repo lint shim installs its managed dependencies."""

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
    """Return the manifest path associated with ``kind`` inside ``directory``."""

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


def _default_runner(args: Sequence[str], cwd: Path | None) -> CompletedProcess[str]:
    """Invoke :func:`run_command` using the configured runner signature."""

    return run_command(args, cwd=cwd, check=False)


def _format_relative(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` when possible."""

    try:
        relative = path.relative_to(root)
    except ValueError:
        return str(path)
    return str(relative) or "."


__all__ = [
    "DEFAULT_STRATEGIES",
    "CommandRunner",
    "ExecutionStatus",
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
