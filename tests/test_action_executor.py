# SPDX-License-Identifier: MIT
"""Behavioural tests for :mod:`pyqa.execution.action_executor`."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from typing import Sequence

import pytest

import sys
import types

_stub_spacy = types.ModuleType("spacy")
_stub_spacy.__version__ = "0.0.0"


def _stub_load(name: str):  # pragma: no cover - helper for stub module
    raise OSError(f"spaCy model '{name}' unavailable in tests")


_stub_spacy.load = _stub_load  # type: ignore[attr-defined]
sys.modules.setdefault("spacy", _stub_spacy)

from pyqa.config import Config
from pyqa.execution.action_executor import (
    ActionExecutor,
    ActionInvocation,
    ExecutionEnvironment,
    ExecutionState,
    OutcomeRecord,
)
from pyqa.execution.cache_context import CacheContext
from pyqa.models import RawDiagnostic, ToolOutcome
from pyqa.tools.base import DeferredCommand, ToolAction, ToolContext


def _build_environment(tmp_path: Path) -> tuple[Config, ExecutionEnvironment]:
    cfg = Config()
    severity_rules: dict[str, list[tuple[object, object]]] = {}
    cache = CacheContext(cache=None, token=None, cache_dir=tmp_path, versions={})
    environment = ExecutionEnvironment(
        config=cfg,
        root=tmp_path,
        severity_rules=severity_rules,
        cache=cache,
    )
    return cfg, environment


def _make_invocation(cfg: Config, root: Path, parser: object | None = None) -> ActionInvocation:
    action = ToolAction(
        name="lint",
        command=DeferredCommand(("fake",)),
        append_files=False,
        parser=parser,
    )
    context = ToolContext(cfg=cfg, root=root)
    return ActionInvocation(
        tool_name="fake",
        action=action,
        context=context,
        command=("fake",),
        env_overrides={},
    )


def _failing_runner(cmd: Sequence[str], *, options=None, **_kwargs) -> CompletedProcess[str]:
    del options
    return CompletedProcess(cmd, returncode=2, stdout="", stderr="first failure line\n")


def test_run_action_logs_warning_without_diagnostics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg, environment = _build_environment(tmp_path)
    invocation = _make_invocation(cfg, tmp_path)
    executor = ActionExecutor(runner=_failing_runner, after_tool_hook=None)

    warnings: list[str] = []

    def capture_warn(msg: str, *, use_emoji: bool, use_color=None) -> None:  # type: ignore[override]
        del use_emoji, use_color
        warnings.append(msg)

    monkeypatch.setattr("pyqa.execution.action_executor.warn", capture_warn)

    outcome = executor.run_action(invocation, environment)

    assert outcome.returncode != 0
    assert not outcome.diagnostics
    assert warnings
    message_lines = warnings[0].splitlines()
    assert message_lines[0] == "fake:lint failed (exit 2)"
    assert any(line.startswith("  command:") for line in message_lines)
    assert any("first failure line" in line for line in message_lines)


class _DiagnosticParser:
    def parse(
        self,
        stdout,
        stderr,
        *,
        context: ToolContext,
    ) -> Sequence[RawDiagnostic]:
        del stdout, stderr, context
        return (
            RawDiagnostic(
                file="pkg/module.py",
                line=1,
                column=None,
                severity="warning",
                message="issue",
                code="W000",
                tool="fake",
            ),
        )


def test_run_action_does_not_log_warning_when_diagnostics_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg, environment = _build_environment(tmp_path)
    invocation = _make_invocation(cfg, tmp_path, parser=_DiagnosticParser())

    def runner(cmd, *, options=None, **_kwargs):
        del options
        return CompletedProcess(cmd, returncode=1, stdout="", stderr="")

    executor = ActionExecutor(runner=runner, after_tool_hook=None)

    warnings: list[str] = []

    def capture_warn(msg: str, *, use_emoji: bool, use_color=None) -> None:  # type: ignore[override]
        del use_emoji, use_color
        warnings.append(msg)

    monkeypatch.setattr("pyqa.execution.action_executor.warn", capture_warn)

    outcome = executor.run_action(invocation, environment)

    assert outcome.returncode != 0
    assert outcome.diagnostics
    assert not warnings


def test_record_outcome_logs_cached_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg, environment = _build_environment(tmp_path)
    invocation = _make_invocation(cfg, tmp_path)
    outcome = ToolOutcome(
        tool="fake",
        action="lint",
        returncode=3,
        stdout=["cached stdout"],
        stderr=["cached stderr"],
        diagnostics=[],
    )
    record = OutcomeRecord(
        order=0,
        invocation=invocation,
        outcome=outcome,
        file_metrics=None,
        from_cache=True,
    )
    executor = ActionExecutor(runner=_failing_runner, after_tool_hook=None)
    warnings: list[str] = []

    def capture_warn(msg: str, *, use_emoji: bool, use_color=None) -> None:  # type: ignore[override]
        del use_emoji, use_color
        warnings.append(msg)

    monkeypatch.setattr("pyqa.execution.action_executor.warn", capture_warn)

    executor.record_outcome(ExecutionState(), environment, record)

    assert warnings
    message_lines = warnings[0].splitlines()
    assert message_lines[0] == "fake:lint failed (exit 3)"
    assert any("--no-cache" in line for line in message_lines)


def test_tombi_adjusts_exit_without_diagnostics(tmp_path: Path) -> None:
    cfg, environment = _build_environment(tmp_path)
    invocation = _make_invocation(cfg, tmp_path)
    invocation = ActionInvocation(
        tool_name="tombi",
        action=invocation.action,
        context=invocation.context,
        command=invocation.command,
        env_overrides=invocation.env_overrides,
    )

    executor = ActionExecutor(runner=_failing_runner, after_tool_hook=None)
    outcome = executor.run_action(invocation, environment)

    assert outcome.returncode == 0
