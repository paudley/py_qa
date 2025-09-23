# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""High level orchestration for running registered lint tools."""

from __future__ import annotations

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from ..config import Config
from ..context import CONTEXT_RESOLVER
from ..diagnostics import (
    build_severity_rules,
    dedupe_outcomes,
    normalize_diagnostics,
)
from ..discovery.base import SupportsDiscovery
from ..environments import inject_node_defaults, prepend_venv_to_path
from ..execution.cache import ResultCache
from ..languages import detect_languages
from ..logging import info, warn
from ..models import RunResult, ToolOutcome
from ..severity import SeverityRuleView
from ..tool_env import CommandPreparer, PreparedCommand
from ..tool_versions import load_versions, save_versions
from ..tools import Tool, ToolAction, ToolContext
from ..tools.registry import ToolRegistry
from .worker import run_command


@dataclass
class OrchestratorHooks:
    """Optional hooks to customise orchestration behaviour."""

    before_tool: Callable[[str], None] | None = None
    after_tool: Callable[[ToolOutcome], None] | None = None


class CommandPreparationService(Protocol):
    """Dependency boundary for preparing commands prior to execution."""

    def prepare(
        self,
        *,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        system_preferred: bool,
        use_local_override: bool,
    ) -> PreparedCommand: ...


class Orchestrator:
    """Coordinates discovery, tool selection, and execution."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        discovery: SupportsDiscovery,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        hooks: OrchestratorHooks | None = None,
        cmd_preparer: CommandPreparationService | None = None,
    ) -> None:
        self._registry = registry
        self._discovery = discovery
        self._runner = runner or run_command
        self._hooks = hooks or OrchestratorHooks()
        self._cmd_preparer = cmd_preparer or CommandPreparer()

    def run(self, cfg: Config, *, root: Path | None = None) -> RunResult:
        root_path = self._prepare_runtime(root)
        matched_files = self._discover_files(cfg, root_path)
        severity_rules = build_severity_rules(cfg.severity_rules)
        cache_ctx = self._initialize_cache(cfg, root_path)
        state = _ExecutionState()

        tool_names = self._select_tools(cfg, matched_files, root_path)
        for name in tool_names:
            if self._process_tool(
                cfg=cfg,
                tool_name=name,
                root=root_path,
                matched_files=matched_files,
                severity_rules=severity_rules,
                cache_ctx=cache_ctx,
                state=state,
            ):
                break

        self._execute_scheduled(cfg, root_path, severity_rules, cache_ctx, state)
        outcomes = [state.outcomes[index] for index in sorted(state.outcomes)]
        result = RunResult(
            root=root_path,
            files=matched_files,
            outcomes=outcomes,
            tool_versions=cache_ctx.versions,
        )
        dedupe_outcomes(result, cfg.dedupe)
        if cache_ctx.cache and cache_ctx.versions_dirty:
            save_versions(cache_ctx.cache_dir, cache_ctx.versions)
        return result

    def _prepare_runtime(self, root: Path | None) -> Path:
        resolved = root or Path.cwd()
        prepend_venv_to_path(resolved)
        inject_node_defaults()
        return resolved

    def _discover_files(self, cfg: Config, root: Path) -> list[Path]:
        matched_files = self._discovery.run(cfg.file_discovery, root)
        limits = [
            entry if entry.is_absolute() else (root / entry)
            for entry in cfg.file_discovery.limit_to
        ]
        limits = [limit.resolve() for limit in limits]
        if limits:
            matched_files = [
                path for path in matched_files if self._is_within_limits(path, limits)
            ]
        info(
            f"Discovered {len(matched_files)} file(s) to lint",
            use_emoji=cfg.output.emoji,
        )
        return matched_files

    def _initialize_cache(self, cfg: Config, root: Path) -> _CacheContext:
        cache_dir = (
            cfg.execution.cache_dir
            if cfg.execution.cache_dir.is_absolute()
            else root / cfg.execution.cache_dir
        )
        if not cfg.execution.cache_enabled:
            return _CacheContext(cache=None, token="", cache_dir=cache_dir, versions={})
        cache = ResultCache(cache_dir)
        token = self._cache_token(cfg)
        versions = load_versions(cache_dir)
        return _CacheContext(
            cache=cache, token=token, cache_dir=cache_dir, versions=versions
        )

    def _process_tool(
        self,
        *,
        cfg: Config,
        tool_name: str,
        root: Path,
        matched_files: Sequence[Path],
        severity_rules: SeverityRuleView,
        cache_ctx: _CacheContext,
        state: "_ExecutionState",
    ) -> bool:
        tool = self._registry.try_get(tool_name)
        if tool is None:
            warn(f"Unknown tool '{tool_name}'", use_emoji=cfg.output.emoji)
            return False
        tool_files = self._filter_files_for_tool(tool.file_extensions, matched_files)
        settings_view = MappingProxyType(dict(cfg.tool_settings.get(tool.name, {})))
        context = ToolContext(
            cfg=cfg, root=root, files=tuple(tool_files), settings=settings_view
        )
        if self._hooks.before_tool:
            self._hooks.before_tool(tool.name)

        for action in tool.actions:
            if not self._should_run_action(cfg, action):
                continue
            prepared = self._cmd_preparer.prepare(
                tool=tool,
                base_cmd=list(action.build_command(context)),
                root=root,
                cache_dir=cfg.execution.cache_dir,
                system_preferred=not cfg.execution.use_local_linters,
                use_local_override=cfg.execution.use_local_linters,
            )
            self._update_tool_version(cache_ctx, tool.name, prepared.version)
            cached = self._load_cached_outcome(
                cache_ctx, tool.name, action, prepared.cmd, context.files
            )
            if cached is not None:
                self._record_outcome(
                    state=state,
                    order=state.order,
                    tool=tool.name,
                    action=action,
                    context=context,
                    cmd=tuple(prepared.cmd),
                    outcome=cached,
                    cache_ctx=cache_ctx,
                )
                if cfg.execution.bail and cached.returncode != 0:
                    state.bail_triggered = True
                    return True
                state.order += 1
                continue

            if action.is_fix:
                outcome = self._run_action(
                    tool.name,
                    action,
                    context,
                    root,
                    severity_rules,
                    prepared.cmd,
                    prepared.env,
                )
                self._record_outcome(
                    state=state,
                    order=state.order,
                    tool=tool.name,
                    action=action,
                    context=context,
                    cmd=tuple(prepared.cmd),
                    outcome=outcome,
                    cache_ctx=cache_ctx,
                )
                state.order += 1
                continue

            if cfg.execution.bail:
                outcome = self._run_action(
                    tool.name,
                    action,
                    context,
                    root,
                    severity_rules,
                    prepared.cmd,
                    prepared.env,
                )
                self._record_outcome(
                    state=state,
                    order=state.order,
                    tool=tool.name,
                    action=action,
                    context=context,
                    cmd=tuple(prepared.cmd),
                    outcome=outcome,
                    cache_ctx=cache_ctx,
                )
                state.order += 1
                if outcome.returncode != 0 and not action.ignore_exit:
                    state.bail_triggered = True
                    return True
                continue

            state.scheduled.append(
                _QueuedAction(
                    order=state.order,
                    tool=tool.name,
                    action=action,
                    context=context,
                    cmd=tuple(prepared.cmd),
                    env=dict(prepared.env),
                )
            )
            state.order += 1
        return False

    def _should_run_action(self, cfg: Config, action: ToolAction) -> bool:
        if cfg.execution.fix_only and not action.is_fix:
            return False
        if cfg.execution.check_only and action.is_fix:
            return False
        return True

    def _update_tool_version(
        self, cache_ctx: "_CacheContext", tool_name: str, version: str | None
    ) -> None:
        if not version:
            return
        if cache_ctx.versions.get(tool_name) == version:
            return
        cache_ctx.versions[tool_name] = version
        cache_ctx.versions_dirty = True

    def _load_cached_outcome(
        self,
        cache_ctx: "_CacheContext",
        tool_name: str,
        action: ToolAction,
        cmd: Sequence[str],
        files: Sequence[Path],
    ) -> ToolOutcome | None:
        if cache_ctx.cache is None:
            return None
        return cache_ctx.cache.load(
            tool=tool_name,
            action=action.name,
            cmd=list(cmd),
            files=list(files),
            token=cache_ctx.token,
        )

    def _execute_scheduled(
        self,
        cfg: Config,
        root: Path,
        severity_rules: SeverityRuleView,
        cache_ctx: "_CacheContext",
        state: "_ExecutionState",
    ) -> None:
        if not state.scheduled:
            return
        if cfg.execution.bail and state.bail_triggered:
            state.scheduled.clear()
            return
        if cfg.execution.jobs > 1:
            with ThreadPoolExecutor(max_workers=cfg.execution.jobs) as executor:
                future_map = {
                    executor.submit(
                        self._run_action,
                        item.tool,
                        item.action,
                        item.context,
                        root,
                        severity_rules,
                        item.cmd,
                        item.env,
                    ): item
                    for item in state.scheduled
                }
                for future in as_completed(future_map):
                    item = future_map[future]
                    outcome = future.result()
                    self._record_outcome(
                        state=state,
                        order=item.order,
                        tool=item.tool,
                        action=item.action,
                        context=item.context,
                        cmd=item.cmd,
                        outcome=outcome,
                        cache_ctx=cache_ctx,
                    )
        else:
            for item in state.scheduled:
                outcome = self._run_action(
                    item.tool,
                    item.action,
                    item.context,
                    root,
                    severity_rules,
                    item.cmd,
                    item.env,
                )
                self._record_outcome(
                    state=state,
                    order=item.order,
                    tool=item.tool,
                    action=item.action,
                    context=item.context,
                    cmd=item.cmd,
                    outcome=outcome,
                    cache_ctx=cache_ctx,
                )

    def _run_action(
        self,
        tool_name: str,
        action,
        context: ToolContext,
        root: Path,
        severity_rules: SeverityRuleView,
        cmd: Sequence[str],
        env_overrides: Mapping[str, str] | None,
    ) -> ToolOutcome:
        env = dict(action.env)
        if env_overrides:
            env.update(env_overrides)
        extra_env = context.settings.get("env")
        if isinstance(extra_env, Mapping):
            env.update({key: str(value) for key, value in extra_env.items()})
        cp = self._runner(list(cmd), cwd=root, env=env, timeout=action.timeout_s)
        extra_filters = context.cfg.output.tool_filters.get(tool_name, [])
        stdout = action.filter_stdout(cp.stdout, extra_filters)
        stderr = action.filter_stderr(cp.stderr, extra_filters)
        parsed: Sequence = ()
        if action.parser:
            parsed = action.parser.parse(stdout, stderr, context=context)
        diagnostics = normalize_diagnostics(
            parsed, tool_name=tool_name, severity_rules=severity_rules
        )
        if diagnostics:
            CONTEXT_RESOLVER.annotate(diagnostics, root=root)
        if cp.returncode != 0 and not action.ignore_exit and context.cfg.output.verbose:
            warn(
                f"{tool_name}:{action.name} exited with {cp.returncode}",
                use_emoji=context.cfg.output.emoji,
            )
        return ToolOutcome(
            tool=tool_name,
            action=action.name,
            returncode=cp.returncode,
            stdout=stdout,
            stderr=stderr,
            diagnostics=diagnostics,
        )

    def _record_outcome(
        self,
        *,
        state: "_ExecutionState",
        order: int,
        tool: str,
        action: ToolAction,
        context: ToolContext,
        cmd: Sequence[str],
        outcome: ToolOutcome,
        cache_ctx: "_CacheContext",
    ) -> None:
        state.outcomes[order] = outcome
        if cache_ctx.cache:
            cache_ctx.cache.store(
                tool=tool,
                action=action.name,
                cmd=list(cmd),
                files=context.files,
                token=cache_ctx.token,
                outcome=outcome,
            )
        if self._hooks.after_tool:
            self._hooks.after_tool(outcome)

    def _select_tools(
        self, cfg: Config, files: Sequence[Path], root: Path
    ) -> Sequence[str]:
        exec_cfg = cfg.execution
        if exec_cfg.only:
            return list(dict.fromkeys(exec_cfg.only))
        languages = (
            list(dict.fromkeys(exec_cfg.languages)) if exec_cfg.languages else []
        )
        if not languages:
            languages = sorted(detect_languages(root, files))
        if languages:
            tool_names: list[str] = []
            for lang in languages:
                tool_names.extend(
                    tool.name for tool in self._registry.tools_for_language(lang)
                )
            if tool_names:
                return list(dict.fromkeys(tool_names))
        return [tool.name for tool in self._registry.tools() if tool.default_enabled]

    @staticmethod
    def _filter_files_for_tool(
        extensions: Sequence[str], files: Sequence[Path]
    ) -> list[Path]:
        if not extensions:
            return list(files)
        patterns = {ext.lower() for ext in extensions}
        filtered: list[Path] = []
        for path in files:
            name = path.name.lower()
            if name in patterns:
                filtered.append(path)
                continue
            suffix = path.suffix.lower()
            if suffix and suffix in patterns:
                filtered.append(path)
                continue
        return filtered

    @staticmethod
    def _cache_token(cfg: Config) -> str:
        exec_cfg = cfg.execution
        components = [
            str(exec_cfg.strict),
            str(exec_cfg.fix_only),
            str(exec_cfg.check_only),
            str(exec_cfg.force_all),
            str(exec_cfg.respect_config),
            str(exec_cfg.line_length),
            ",".join(sorted(cfg.severity_rules)),
        ]
        if cfg.tool_settings:
            serialized = json.dumps(cfg.tool_settings, sort_keys=True)
            digest = hashlib.sha1(
                serialized.encode("utf-8"), usedforsecurity=False
            ).hexdigest()
            components.append(digest)
        return "|".join(components)

    @staticmethod
    def _is_within_limits(candidate: Path, limits: Sequence[Path]) -> bool:
        if not limits:
            return True
        for limit in limits:
            try:
                candidate.relative_to(limit)
                return True
            except ValueError:
                continue
        return False


class _QueuedAction(BaseModel):
    order: int
    tool: str
    action: ToolAction
    context: ToolContext
    cmd: tuple[str, ...]
    env: Mapping[str, str]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("cmd", mode="before")
    @classmethod
    def _coerce_cmd(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, tuple):
            return value
        if isinstance(value, (list, Sequence)):
            return tuple(str(entry) for entry in value)
        if isinstance(value, str):
            return (value,)
        raise TypeError("cmd must be a sequence of strings")

    @field_validator("env", mode="before")
    @classmethod
    def _coerce_env(cls, value: object) -> Mapping[str, str]:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return {str(k): str(v) for k, v in value.items()}
        raise TypeError("env must be a mapping of strings")


@dataclass
class _CacheContext:
    cache: ResultCache | None
    token: str
    cache_dir: Path
    versions: dict[str, str]
    versions_dirty: bool = False


@dataclass
class _ExecutionState:
    outcomes: dict[int, ToolOutcome] = field(default_factory=dict)
    scheduled: list[_QueuedAction] = field(default_factory=list)
    order: int = 0
    bail_triggered: bool = False
