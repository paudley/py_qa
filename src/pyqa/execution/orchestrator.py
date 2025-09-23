# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""High level orchestration for running registered lint tools."""

from __future__ import annotations

import hashlib
import json
import subprocess  # nosec B404 - required for executing configured tool commands
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

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
from ..tool_env import CommandPreparer
from ..tool_versions import load_versions, save_versions
from ..tools import ToolAction, ToolContext
from ..tools.registry import ToolRegistry
from .worker import run_command


@dataclass
class OrchestratorHooks:
    """Optional hooks to customise orchestration behaviour."""

    before_tool: Callable[[str], None] | None = None
    after_tool: Callable[[ToolOutcome], None] | None = None


class Orchestrator:
    """Coordinates discovery, tool selection, and execution."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        discovery: SupportsDiscovery,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        hooks: OrchestratorHooks | None = None,
    ) -> None:
        self._registry = registry
        self._discovery = discovery
        self._runner = runner or run_command
        self._hooks = hooks or OrchestratorHooks()
        self._cmd_preparer = CommandPreparer()

    def run(self, cfg: Config, *, root: Path | None = None) -> RunResult:
        root = root or Path.cwd()
        prepend_venv_to_path(root)
        inject_node_defaults()

        matched_files = self._discovery.run(cfg.file_discovery, root)
        limits = [entry if entry.is_absolute() else (root / entry) for entry in cfg.file_discovery.limit_to]
        limits = [limit.resolve() for limit in limits]
        if limits:
            matched_files = [path for path in matched_files if self._is_within_limits(path, limits)]
        info(
            f"Discovered {len(matched_files)} file(s) to lint",
            use_emoji=cfg.output.emoji,
        )

        tool_names = self._select_tools(cfg, matched_files, root)
        severity_rules: SeverityRuleView = build_severity_rules(cfg.severity_rules)
        cache_dir = cfg.execution.cache_dir if cfg.execution.cache_dir.is_absolute() else root / cfg.execution.cache_dir
        cache = ResultCache(cache_dir) if cfg.execution.cache_enabled else None
        token = self._cache_token(cfg) if cache else ""
        tool_versions = load_versions(cache_dir) if cache else {}
        versions_dirty = False
        scheduled: list[_QueuedAction] = []
        outcome_map: dict[int, ToolOutcome] = {}
        order = 0
        bail_triggered = False

        for name in tool_names:
            tool = self._registry.try_get(name)
            if not tool:
                warn(f"Unknown tool '{name}'", use_emoji=cfg.output.emoji)
                continue
            tool_files = self._filter_files_for_tool(tool.file_extensions, matched_files)
            settings_view = MappingProxyType(dict(cfg.tool_settings.get(tool.name, {})))
            context = ToolContext(
                cfg=cfg,
                root=root,
                files=tool_files,
                settings=settings_view,
            )
            if self._hooks.before_tool:
                self._hooks.before_tool(tool.name)
            for action in tool.actions:
                if cfg.execution.fix_only and not action.is_fix:
                    continue
                if cfg.execution.check_only and action.is_fix:
                    continue
                cmd = list(action.build_command(context))
                prepared = self._cmd_preparer.prepare(
                    tool=tool,
                    base_cmd=cmd,
                    root=root,
                    cache_dir=cfg.execution.cache_dir,
                    system_preferred=not cfg.execution.use_local_linters,
                    use_local_override=cfg.execution.use_local_linters,
                )
                actual_cmd = prepared.cmd
                extra_env = prepared.env
                if prepared.version and tool_versions.get(tool.name) != prepared.version:
                    tool_versions[tool.name] = prepared.version
                    versions_dirty = True

                if cache:
                    cached = cache.load(
                        tool=tool.name,
                        action=action.name,
                        cmd=actual_cmd,
                        files=tool_files,
                        token=token,
                    )
                    if cached:
                        outcome_map[order] = cached
                        if self._hooks.after_tool:
                            self._hooks.after_tool(cached)
                        order += 1
                        if cfg.execution.bail and cached.returncode != 0:
                            bail_triggered = True
                            break
                        continue

                if action.is_fix:
                    outcome = self._run_action(
                        tool.name,
                        action,
                        context,
                        root,
                        severity_rules,
                        actual_cmd,
                        extra_env,
                    )
                    outcome_map[order] = outcome
                    if cache:
                        cache.store(
                            tool=tool.name,
                            action=action.name,
                            cmd=actual_cmd,
                            files=context.files,
                            token=token,
                            outcome=outcome,
                        )
                    if self._hooks.after_tool:
                        self._hooks.after_tool(outcome)
                    order += 1
                    continue

                if cfg.execution.bail:
                    outcome = self._run_action(
                        tool.name,
                        action,
                        context,
                        root,
                        severity_rules,
                        actual_cmd,
                        extra_env,
                    )
                    outcome_map[order] = outcome
                    if cache:
                        cache.store(
                            tool=tool.name,
                            action=action.name,
                            cmd=actual_cmd,
                            files=context.files,
                            token=token,
                            outcome=outcome,
                        )
                    if self._hooks.after_tool:
                        self._hooks.after_tool(outcome)
                    order += 1
                    if outcome.returncode != 0 and not action.ignore_exit:
                        bail_triggered = True
                        break
                else:
                    scheduled.append(
                        _QueuedAction(
                            order=order,
                            tool=tool.name,
                            action=action,
                            context=context,
                            cmd=actual_cmd,
                            env=dict(extra_env),
                        )
                    )
                    order += 1
            if cfg.execution.bail and bail_triggered:
                break
        if cfg.execution.bail and bail_triggered:
            scheduled = []

        if scheduled:
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
                        for item in scheduled
                    }
                    for future in as_completed(future_map):
                        item = future_map[future]
                        outcome = future.result()
                        outcome_map[item.order] = outcome
                        if cache:
                            cache.store(
                                tool=item.tool,
                                action=item.action.name,
                                cmd=item.cmd,
                                files=item.context.files,
                                token=token,
                                outcome=outcome,
                            )
                        if self._hooks.after_tool:
                            self._hooks.after_tool(outcome)
            else:
                for item in scheduled:
                    outcome = self._run_action(
                        item.tool,
                        item.action,
                        item.context,
                        root,
                        severity_rules,
                        item.cmd,
                        item.env,
                    )
                    outcome_map[item.order] = outcome
                    if cache:
                        cache.store(
                            tool=item.tool,
                            action=item.action.name,
                            cmd=item.cmd,
                            files=item.context.files,
                            token=token,
                            outcome=outcome,
                        )
                    if self._hooks.after_tool:
                        self._hooks.after_tool(outcome)

        outcomes = [outcome_map[i] for i in sorted(outcome_map)] if outcome_map else []
        result = RunResult(
            root=root,
            files=matched_files,
            outcomes=outcomes,
            tool_versions=tool_versions,
        )
        dedupe_outcomes(result, cfg.dedupe)
        if cache and versions_dirty:
            save_versions(cache_dir, tool_versions)
        return result

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
        diagnostics = normalize_diagnostics(parsed, tool_name=tool_name, severity_rules=severity_rules)
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

    def _select_tools(self, cfg: Config, files: Sequence[Path], root: Path) -> Sequence[str]:
        exec_cfg = cfg.execution
        if exec_cfg.only:
            return list(dict.fromkeys(exec_cfg.only))
        languages = list(dict.fromkeys(exec_cfg.languages)) if exec_cfg.languages else []
        if not languages:
            languages = sorted(detect_languages(root, files))
        if languages:
            tool_names: list[str] = []
            for lang in languages:
                tool_names.extend(tool.name for tool in self._registry.tools_for_language(lang))
            if tool_names:
                return list(dict.fromkeys(tool_names))
        return [tool.name for tool in self._registry.tools() if tool.default_enabled]

    @staticmethod
    def _filter_files_for_tool(extensions: Sequence[str], files: Sequence[Path]) -> list[Path]:
        if not extensions:
            return list(files)
        suffixes = {ext.lower() for ext in extensions if ext.startswith('.')}
        names = {ext.lower() for ext in extensions if not ext.startswith('.')}
        filtered: list[Path] = []
        for path in files:
            suffix = path.suffix.lower()
            name = path.name.lower()
            if suffixes and suffix in suffixes:
                filtered.append(path)
                continue
            if names and name in names:
                filtered.append(path)
                continue
        if not suffixes and names:
            return filtered
        if not names and suffixes:
            return filtered
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
            digest = hashlib.sha1(serialized.encode("utf-8"), usedforsecurity=False).hexdigest()
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


@dataclass
class _QueuedAction:
    order: int
    tool: str
    action: ToolAction
    context: ToolContext
    cmd: list[str]
    env: Mapping[str, str]
