# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""High level orchestration for running registered lint tools."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from ..analysis import apply_change_impact, apply_suppression_hints, build_refactor_navigator
from ..annotations import AnnotationEngine
from ..config import Config
from ..context import CONTEXT_RESOLVER
from ..diagnostics import (
    build_severity_rules,
    dedupe_outcomes,
    normalize_diagnostics,
)
from ..discovery.base import SupportsDiscovery
from ..environments import inject_node_defaults, prepend_venv_to_path
from ..execution.cache import CachedEntry, ResultCache
from ..filesystem.paths import normalize_path_key
from ..languages import detect_languages
from ..logging import info, warn
from ..metrics import FileMetrics, compute_file_metrics
from ..models import Diagnostic, RunResult, ToolOutcome
from ..severity import SeverityRuleView
from ..tool_env import CommandPreparer, PreparedCommand
from ..tool_versions import load_versions, save_versions
from ..tools import Tool, ToolAction, ToolContext
from ..tools.registry import ToolRegistry
from .worker import run_command

FetchEvent = Literal["start", "completed", "error"]

_PHASE_ORDER: tuple[str, ...] = (
    "format",
    "lint",
    "analysis",
    "security",
    "test",
    "coverage",
    "utility",
)


_ANALYSIS_ENGINE = AnnotationEngine()
FetchCallback = Callable[[FetchEvent, str, str, int, int, str | None], None]


def _filter_diagnostics(
    diagnostics: Sequence[Diagnostic],
    tool_name: str,
    patterns: Sequence[str],
    root: Path,
) -> list[Diagnostic]:
    """Remove diagnostics matching suppression patterns for *tool_name*."""
    if not diagnostics:
        return []

    compiled = [re.compile(pattern) for pattern in patterns] if patterns else []
    kept: list[Diagnostic] = []
    seen_duplicate_groups: set[tuple[str, ...]] = set()
    duplicate_codes = {"R0801", "DUPLICATE-CODE"}
    for diagnostic in diagnostics:
        tool = diagnostic.tool or tool_name
        location = diagnostic.file or "<unknown>"
        if diagnostic.line is not None:
            location = f"{location}:{diagnostic.line}"
            if diagnostic.function:
                location = f"{location}:{diagnostic.function}"
        elif diagnostic.function:
            location = f"{location}:{diagnostic.function}"

        code = diagnostic.code or "-"
        message = diagnostic.message.splitlines()[0].strip()
        candidate = f"{tool}, {location}, {code}, {message}"

        if compiled and any(pattern.search(candidate) for pattern in compiled):
            continue

        upper_code = (diagnostic.code or "").upper()
        if tool == "pylint" and upper_code in duplicate_codes:
            entries = _collect_duplicate_code_entries(diagnostic.message, root)
            group_key = _duplicate_group_key(entries)
            if group_key:
                if group_key in seen_duplicate_groups:
                    continue
                seen_duplicate_groups.add(group_key)
                preferred = _select_duplicate_primary(entries, diagnostic, root)
                if preferred:
                    diagnostic.file = preferred.path
                    if preferred.line is not None:
                        diagnostic.line = preferred.line

            lines = diagnostic.message.splitlines()
            snippet: list[str] = []
            for entry in lines[1:]:
                stripped = entry.lstrip()
                if not stripped or stripped.startswith("=="):
                    continue
                snippet.append(stripped)
            context_line = (diagnostic.function or "").lstrip()
            if context_line.startswith("#"):
                continue
            source_line = None
            if diagnostic.line is not None and diagnostic.file:
                source_line = _read_source_line(root, diagnostic.file, diagnostic.line)
            if snippet and snippet[0].startswith("#"):
                continue
            if source_line is not None and source_line.lstrip().startswith("#"):
                continue

        suppressed_codes = duplicate_codes | {"W0613", "W0212"}
        if (
            tool == "pylint"
            and upper_code in suppressed_codes
            and diagnostic.file
            and "tests/" in diagnostic.file.replace("\\", "/")
        ):
            continue

        kept.append(diagnostic)
    return kept


def _read_source_line(root: Path, file_str: str, line_no: int) -> str | None:
    candidate = Path(file_str)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    try:
        with candidate.open("r", encoding="utf-8", errors="ignore") as handle:
            for idx, line in enumerate(handle, start=1):
                if idx == line_no:
                    return line.rstrip("\n")
    except OSError:
        return None
    return None


class _DuplicateCodeEntry(NamedTuple):
    """Details extracted from a pylint duplicate-code diagnostic."""

    key: str
    path: str
    line: int | None


def _collect_duplicate_code_entries(message: str, root: Path) -> list[_DuplicateCodeEntry]:
    """Extract duplicate-code targets from ``message`` with normalised metadata."""
    entries: list[_DuplicateCodeEntry] = []
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    details: list[str] = []

    for line in lines[1:]:
        if line.startswith("=="):
            details.append(line[2:].strip())

    if not details and lines:
        _, _, suffix = lines[0].partition(":")
        if suffix:
            for candidate in suffix.split(","):
                token = candidate.strip()
                if token:
                    details.append(token)

    for detail in details:
        name, span = _split_duplicate_code_entry(detail)
        if not name:
            continue
        path = _resolve_duplicate_target(name, root)
        span_token = span.strip()
        try:
            key_path = normalize_path_key(path, base_dir=root)
        except ValueError:
            key_path = path.replace("\\", "/")
        key = key_path.lower()
        if span_token:
            key = f"{key}|{span_token.lower()}"
        entries.append(
            _DuplicateCodeEntry(
                key=key,
                path=path,
                line=_parse_duplicate_line(span_token),
            ),
        )
    return entries


_TRAILING_SPAN = re.compile(r":(?P<start>\d+)(?::(?P<end>\d+))?\s*$")


def _split_duplicate_code_entry(entry: str) -> tuple[str, str]:
    """Split ``entry`` into the referenced module/file name and line span."""
    stripped = entry.strip()
    bracket_index = stripped.find("[")
    if bracket_index != -1:
        name = stripped[:bracket_index].rstrip(":")
        span = stripped[bracket_index:]
        return name.strip(), span.strip()

    match = _TRAILING_SPAN.search(stripped)
    if match:
        name = stripped[: match.start()].rstrip(":")
        start = match.group("start")
        end = match.group("end")
        if end:
            span = f"[{start}:{end}]"
        else:
            span = f"[{start}]"
        return name.strip(), span

    return stripped, ""


def _parse_duplicate_line(span: str) -> int | None:
    """Return the starting line from a duplicate-code span like ``[12:18]``."""
    cleaned = span.strip()[1:-1] if span.startswith("[") and span.endswith("]") else span.strip()
    head, _, _ = cleaned.partition(":")
    try:
        return int(head)
    except ValueError:
        return None


def _duplicate_group_key(entries: Sequence[_DuplicateCodeEntry]) -> tuple[str, ...]:
    """Build a stable key describing a duplicate-code diagnostic group."""
    if not entries:
        return ()
    unique_keys = {entry.key for entry in entries}
    return tuple(sorted(unique_keys))


def _select_duplicate_primary(
    entries: Sequence[_DuplicateCodeEntry],
    diagnostic: Diagnostic,
    root: Path,
) -> _DuplicateCodeEntry | None:
    """Choose which duplicate entry should anchor the diagnostic location."""
    if not entries:
        return None

    current = _normalise_duplicate_path(diagnostic.file or "", root)
    for entry in entries:
        if current and _normalise_duplicate_path(entry.path, root) == current:
            return entry

    for entry in entries:
        if not _is_test_path(entry.path):
            return entry

    return entries[0]


def _normalise_duplicate_path(path: str, root: Path) -> str:
    """Return a normalised comparison key for ``path`` relative to ``root``."""
    if not path:
        return ""
    try:
        return normalize_path_key(path, base_dir=root)
    except ValueError:
        return path.replace("\\", "/")


def _is_test_path(path: str) -> bool:
    """Return ``True`` when ``path`` points inside a tests directory."""
    normalized = path.replace("\\", "/").lower()
    return normalized.startswith("tests/") or "/tests/" in normalized


def _resolve_duplicate_target(name: str, root: Path) -> str:
    """Resolve a pylint duplicate-code target to a stable display path."""
    variants = _generate_duplicate_variants(name)

    for variant in variants:
        candidate = Path(variant)
        if candidate.is_absolute() and candidate.exists():
            return normalize_path_key(candidate, base_dir=root)

    search_prefixes = ("", "src/", "tests/", "tooling/", "docs/", "ref_docs/")
    for variant in variants:
        for prefix in search_prefixes:
            candidate = root / prefix / variant
            if candidate.exists():
                return normalize_path_key(candidate, base_dir=root)

    fallback_candidates = [
        variant
        for variant in variants
        if "/" in variant and Path(variant).suffix in {".py", ".pyi"}
    ]
    if not fallback_candidates:
        fallback_candidates = [variant for variant in variants if "/" in variant]
    if not fallback_candidates:
        fallback_candidates = list(variants)

    fallback = fallback_candidates[0] if fallback_candidates else name.strip().replace("\\", "/")
    fallback = fallback.lstrip("./")
    if Path(fallback).suffix == "":
        fallback = f"{fallback}.py"
    try:
        return normalize_path_key(fallback, base_dir=root)
    except ValueError:
        return fallback


def _generate_duplicate_variants(name: str) -> list[str]:
    """Return candidate path variants for a duplicate-code entry name."""
    token = name.strip().strip("\"'")
    token = token.replace("\\", "/")
    if not token:
        return []

    base_variants = [token]
    dotted = token.replace(".", "/")
    if dotted != token:
        base_variants.append(dotted)

    seen: set[str] = set()
    variants: list[str] = []
    for variant in base_variants:
        cleaned = variant.lstrip("./")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            variants.append(cleaned)
        if cleaned and Path(cleaned).suffix == "":
            with_ext = f"{cleaned}.py"
            if with_ext not in seen:
                seen.add(with_ext)
                variants.append(with_ext)
            if not cleaned.endswith("__init__"):
                init_variant = f"{cleaned}/__init__.py"
                if init_variant not in seen:
                    seen.add(init_variant)
                    variants.append(init_variant)
    return variants


@dataclass
class OrchestratorHooks:
    """Optional hooks to customise orchestration behaviour."""

    before_tool: Callable[[str], None] | None = None
    after_tool: Callable[[ToolOutcome], None] | None = None
    after_discovery: Callable[[int], None] | None = None
    after_execution: Callable[[RunResult], None] | None = None
    after_plan: Callable[[int], None] | None = None


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
        runner: Callable[..., Any] | None = None,
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
        if self._hooks.after_discovery:
            self._hooks.after_discovery(len(matched_files))
        if self._hooks.after_plan:
            total_actions = 0
            for name in tool_names:
                tool = self._registry.try_get(name)
                if tool is None:
                    continue
                for action in tool.actions:
                    if self._should_run_action(cfg, action):
                        total_actions += 1
            self._hooks.after_plan(total_actions)
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
        self._populate_missing_metrics(state, matched_files)
        result = RunResult(
            root=root_path,
            files=matched_files,
            outcomes=outcomes,
            tool_versions=cache_ctx.versions,
            file_metrics=dict(state.file_metrics),
        )
        dedupe_outcomes(result, cfg.dedupe)
        _ANALYSIS_ENGINE.annotate_run(result)
        apply_suppression_hints(result, _ANALYSIS_ENGINE)
        apply_change_impact(result)
        build_refactor_navigator(result, _ANALYSIS_ENGINE)
        if cache_ctx.cache and cache_ctx.versions_dirty:
            save_versions(cache_ctx.cache_dir, cache_ctx.versions)
        if self._hooks.after_execution:
            self._hooks.after_execution(result)
        return result

    def fetch_all_tools(
        self,
        cfg: Config,
        *,
        root: Path | None = None,
        callback: FetchCallback | None = None,
    ) -> list[tuple[str, str, PreparedCommand | None, str | None]]:
        """Prepare every tool action to warm caches without executing them."""
        root_path = self._prepare_runtime(root)
        cache_dir = (
            cfg.execution.cache_dir
            if cfg.execution.cache_dir.is_absolute()
            else root_path / cfg.execution.cache_dir
        )
        system_preferred = not cfg.execution.use_local_linters
        use_local_override = cfg.execution.use_local_linters
        ordered_names = self._order_tools([tool.name for tool in self._registry.tools()])
        tool_actions: list[tuple[Tool, ToolAction]] = []
        for name in ordered_names:
            tool = self._registry.try_get(name)
            if tool is None:
                continue
            for action in tool.actions:
                tool_actions.append((tool, action))
        total = len(tool_actions)
        results: list[tuple[str, str, PreparedCommand | None, str | None]] = []
        installed_tools: set[str] = set()
        for index, (tool, action) in enumerate(tool_actions, start=1):
            if callback:
                callback("start", tool.name, action.name, index, total, None)
            settings_view = MappingProxyType(dict(cfg.tool_settings.get(tool.name, {})))
            context = ToolContext(
                cfg=cfg,
                root=root_path,
                files=tuple(),
                settings=settings_view,
            )
            self._apply_installers(tool, context, installed_tools)
            base_cmd = list(action.build_command(context))
            try:
                prepared = self._cmd_preparer.prepare(
                    tool=tool,
                    base_cmd=base_cmd,
                    root=root_path,
                    cache_dir=cache_dir,
                    system_preferred=system_preferred,
                    use_local_override=use_local_override,
                )
                results.append((tool.name, action.name, prepared, None))
                if callback:
                    callback(
                        "completed",
                        tool.name,
                        action.name,
                        index,
                        total,
                        None,
                    )
            except RuntimeError as exc:  # installation or preparation failure
                results.append((tool.name, action.name, None, str(exc)))
                if callback:
                    callback(
                        "error",
                        tool.name,
                        action.name,
                        index,
                        total,
                        str(exc),
                    )
        return results

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
            matched_files = [path for path in matched_files if self._is_within_limits(path, limits)]
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
            return _CacheContext(cache=None, token=None, cache_dir=cache_dir, versions={})
        cache = ResultCache(cache_dir)
        token = self._cache_token(cfg)
        versions = load_versions(cache_dir)
        return _CacheContext(cache=cache, token=token, cache_dir=cache_dir, versions=versions)

    def _process_tool(
        self,
        *,
        cfg: Config,
        tool_name: str,
        root: Path,
        matched_files: Sequence[Path],
        severity_rules: SeverityRuleView,
        cache_ctx: _CacheContext,
        state: _ExecutionState,
    ) -> bool:
        tool = self._registry.try_get(tool_name)
        if tool is None:
            warn(f"Unknown tool '{tool_name}'", use_emoji=cfg.output.emoji)
            return False
        tool_files = self._filter_files_for_tool(tool.file_extensions, matched_files)
        settings_view = MappingProxyType(dict(cfg.tool_settings.get(tool.name, {})))
        context = ToolContext(cfg=cfg, root=root, files=tuple(tool_files), settings=settings_view)
        self._apply_installers(tool, context, state.installed_tools)
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
            cached_entry = self._load_cached_outcome(
                cache_ctx,
                tool.name,
                action,
                prepared.cmd,
                context.files,
            )
            if cached_entry is not None:
                outcome = cached_entry.outcome
                self._record_outcome(
                    state=state,
                    order=state.order,
                    tool=tool.name,
                    action=action,
                    context=context,
                    cmd=tuple(prepared.cmd),
                    outcome=outcome,
                    file_metrics=cached_entry.file_metrics,
                    cache_ctx=cache_ctx,
                    from_cache=True,
                )
                if cfg.execution.bail and outcome.returncode != 0:
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
                    file_metrics=None,
                    cache_ctx=cache_ctx,
                    from_cache=False,
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
                    file_metrics=None,
                    cache_ctx=cache_ctx,
                    from_cache=False,
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
                ),
            )
            state.order += 1
        return False

    def _should_run_action(self, cfg: Config, action: ToolAction) -> bool:
        if cfg.execution.fix_only and not action.is_fix:
            return False
        if cfg.execution.check_only and action.is_fix:
            return False
        return True

    def _apply_installers(
        self,
        tool: Tool,
        context: ToolContext,
        installed: set[str],
    ) -> None:
        if not tool.installers or tool.name in installed:
            return
        for installer in tool.installers:
            installer(context)
        installed.add(tool.name)

    def _update_tool_version(
        self,
        cache_ctx: _CacheContext,
        tool_name: str,
        version: str | None,
    ) -> None:
        if not version:
            return
        if cache_ctx.versions.get(tool_name) == version:
            return
        cache_ctx.versions[tool_name] = version
        cache_ctx.versions_dirty = True

    def _load_cached_outcome(
        self,
        cache_ctx: _CacheContext,
        tool_name: str,
        action: ToolAction,
        cmd: Sequence[str],
        files: Sequence[Path],
    ) -> CachedEntry | None:
        if cache_ctx.cache is None or cache_ctx.token is None:
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
        cache_ctx: _CacheContext,
        state: _ExecutionState,
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
                        file_metrics=None,
                        cache_ctx=cache_ctx,
                        from_cache=False,
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
                    file_metrics=None,
                    cache_ctx=cache_ctx,
                    from_cache=False,
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
        stdout_text = action.filter_stdout(cp.stdout, extra_filters)
        stderr_text = action.filter_stderr(cp.stderr, extra_filters)
        stdout_lines = stdout_text.splitlines()
        stderr_lines = stderr_text.splitlines()
        parsed: Sequence = ()
        if action.parser:
            parsed = action.parser.parse(stdout_lines, stderr_lines, context=context)
        diagnostics = normalize_diagnostics(
            parsed,
            tool_name=tool_name,
            severity_rules=severity_rules,
        )
        diagnostics = _filter_diagnostics(diagnostics, tool_name, extra_filters, root)
        adjusted_returncode = cp.returncode
        if tool_name == "pylint" and not diagnostics:
            adjusted_returncode = 0

        if diagnostics:
            CONTEXT_RESOLVER.annotate(diagnostics, root=root)
        if adjusted_returncode != 0 and not action.ignore_exit and context.cfg.output.verbose:
            warn(
                f"{tool_name}:{action.name} exited with {cp.returncode}",
                use_emoji=context.cfg.output.emoji,
            )
        return ToolOutcome(
            tool=tool_name,
            action=action.name,
            returncode=adjusted_returncode,
            stdout=stdout_lines,
            stderr=stderr_lines,
            diagnostics=diagnostics,
        )

    def _record_outcome(
        self,
        *,
        state: _ExecutionState,
        order: int,
        tool: str,
        action: ToolAction,
        context: ToolContext,
        cmd: Sequence[str],
        outcome: ToolOutcome,
        cache_ctx: _CacheContext,
        file_metrics: Mapping[str, FileMetrics] | None,
        from_cache: bool,
    ) -> None:
        metrics_map = (
            dict(file_metrics)
            if file_metrics is not None
            else self._collect_metrics_for_files(state, context.files)
        )
        self._update_state_metrics(state, metrics_map)
        state.outcomes[order] = outcome
        if cache_ctx.cache and cache_ctx.token is not None and not from_cache:
            cache_ctx.cache.store(
                tool=tool,
                action=action.name,
                cmd=list(cmd),
                files=context.files,
                token=cache_ctx.token,
                outcome=outcome,
                file_metrics=metrics_map,
            )
        if self._hooks.after_tool:
            self._hooks.after_tool(outcome)

    def _select_tools(self, cfg: Config, files: Sequence[Path], root: Path) -> Sequence[str]:
        exec_cfg = cfg.execution
        if exec_cfg.only:
            return self._order_tools(dict.fromkeys(exec_cfg.only))
        languages = list(dict.fromkeys(exec_cfg.languages)) if exec_cfg.languages else []
        if not languages:
            languages = sorted(detect_languages(root, files))
        if languages:
            tool_names: list[str] = []
            for lang in languages:
                tool_names.extend(tool.name for tool in self._registry.tools_for_language(lang))
            if tool_names:
                return self._order_tools(dict.fromkeys(tool_names))
        default_tools = [tool.name for tool in self._registry.tools() if tool.default_enabled]
        return self._order_tools(dict.fromkeys(default_tools))

    def _order_tools(self, tool_names: Mapping[str, None] | Sequence[str]) -> list[str]:
        if isinstance(tool_names, Mapping):
            ordered_input = list(tool_names.keys())
        else:
            ordered_input = list(dict.fromkeys(tool_names))
        tools: dict[str, Tool] = {}
        for name in ordered_input:
            tool = self._registry.try_get(name)
            if tool is not None:
                tools[name] = tool
        filtered = [name for name in ordered_input if name in tools]
        if not filtered:
            return []

        phase_groups: dict[str, list[str]] = {}
        unknown_phases: list[str] = []
        for name in filtered:
            tool = tools[name]
            phase = getattr(tool, "phase", "lint")
            phase_groups.setdefault(phase, []).append(name)
            if phase not in _PHASE_ORDER and phase not in unknown_phases:
                unknown_phases.append(phase)

        fallback_index = {name: index for index, name in enumerate(filtered)}
        ordered: list[str] = []

        for phase in _PHASE_ORDER:
            names = phase_groups.get(phase)
            if not names:
                continue
            ordered.extend(self._order_phase(names, tools, fallback_index))

        for phase in sorted(unknown_phases):
            names = phase_groups.get(phase)
            if names:
                ordered.extend(self._order_phase(names, tools, fallback_index))

        remaining = [name for name in filtered if name not in ordered]
        ordered.extend(remaining)
        return ordered

    @staticmethod
    def _order_phase(
        names: Sequence[str],
        tools: Mapping[str, Tool],
        fallback_index: Mapping[str, int],
    ) -> list[str]:
        if len(names) <= 1:
            return list(names)

        dependencies: dict[str, set[str]] = {name: set() for name in names}
        for name in names:
            tool = tools[name]
            for dep in getattr(tool, "after", ()):  # tools that must precede this one
                if dep in dependencies:
                    dependencies[name].add(dep)
            for succ in getattr(tool, "before", ()):  # tools that must follow this one
                if succ in dependencies:
                    dependencies[succ].add(name)

        remaining = {name: set(deps) for name, deps in dependencies.items()}
        ready = sorted(
            [name for name, deps in remaining.items() if not deps],
            key=lambda item: fallback_index.get(item, 0),
        )
        ordered: list[str] = []

        while ready:
            current = ready.pop(0)
            ordered.append(current)
            remaining.pop(current, None)
            for other in list(remaining.keys()):
                deps = remaining[other]
                if current in deps:
                    deps.remove(current)
                    if not deps and other not in ready:
                        ready.append(other)
            ready.sort(key=lambda item: fallback_index.get(item, 0))

        if remaining:
            return list(names)
        return ordered

    @staticmethod
    def _filter_files_for_tool(extensions: Sequence[str], files: Sequence[Path]) -> list[Path]:
        if not extensions:
            normalised = {path if path.is_absolute() else path.resolve() for path in files}
            return sorted(normalised, key=lambda item: str(item))

        patterns = {ext.lower() for ext in extensions}
        filtered: set[Path] = set()
        for path in files:
            resolved = path if path.is_absolute() else path.resolve()
            name = resolved.name.lower()
            if name in patterns:
                filtered.add(resolved)
                continue
            suffix = resolved.suffix.lower()
            if suffix and suffix in patterns:
                filtered.add(resolved)
                continue
        return sorted(filtered, key=lambda item: str(item))

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

    def _populate_missing_metrics(self, state: _ExecutionState, files: Sequence[Path]) -> None:
        for path in files:
            key = normalize_path_key(path)
            if key in state.file_metrics:
                continue
            state.file_metrics[key] = compute_file_metrics(path)

    def _collect_metrics_for_files(
        self,
        state: _ExecutionState,
        files: Sequence[Path],
    ) -> dict[str, FileMetrics]:
        collected: dict[str, FileMetrics] = {}
        for path in files:
            key = normalize_path_key(path)
            metric = state.file_metrics.get(key)
            if metric is None:
                metric = compute_file_metrics(path)
            metric.ensure_labels()
            collected[key] = metric
        return collected

    @staticmethod
    def _update_state_metrics(state: _ExecutionState, metrics: Mapping[str, FileMetrics]) -> None:
        for key, metric in metrics.items():
            metric.ensure_labels()
            state.file_metrics[key] = metric

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
    token: str | None
    cache_dir: Path
    versions: dict[str, str]
    versions_dirty: bool = False


@dataclass
class _ExecutionState:
    outcomes: dict[int, ToolOutcome] = field(default_factory=dict)
    scheduled: list[_QueuedAction] = field(default_factory=list)
    order: int = 0
    bail_triggered: bool = False
    file_metrics: dict[str, FileMetrics] = field(default_factory=dict)
    installed_tools: set[str] = field(default_factory=set)
