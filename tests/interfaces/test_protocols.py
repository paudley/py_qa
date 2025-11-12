# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from pathlib import Path

from rich.console import Console

from pyqa.core.serialization import JsonValue
from pyqa.interfaces.analysis import AnnotationProvider, MessageSpan
from pyqa.interfaces.catalog import (
    CatalogSnapshot,
    StrategyFactory,
    StrategyRequest,
    ToolDefinition,
)
from pyqa.cli.protocols import CliCommand, CliCommandFactory, CliInvocation
from pyqa.interfaces.compliance import ComplianceCheck, PolicyEvaluator, RemediationService
from pyqa.interfaces.config import ConfigMutator, ConfigResolver, ConfigSource
from pyqa.interfaces.core import ConsoleFactory, LoggerFactory, Serializer
from pyqa.interfaces.discovery import DiscoveryStrategy, ExcludePolicy, TargetPlanner
from pyqa.interfaces.environment import EnvironmentPreparer, RuntimeResolver, WorkspaceLocator
from pyqa.interfaces.orchestration import ActionExecutor, ExecutionPipeline, RunHooks
from pyqa.interfaces.reporting import AdviceProvider, DiagnosticPresenter


class _Span:
    start = 0
    end = 1
    kind = "argument"
    style = "ansi256:0"


class _AnnotationProvider:
    def annotate_run(self, result):
        return {}

    def message_spans(self, message: str):
        return [_Span()]

    def message_signature(self, message: str):
        return ()


def test_annotation_provider_protocol() -> None:
    assert isinstance(_Span(), MessageSpan)
    assert isinstance(_AnnotationProvider(), AnnotationProvider)


class _Tool(ToolDefinition):
    name = "demo"
    phase = "lint"
    languages = ("python",)

    def to_dict(self) -> Mapping[str, str]:
        return {"name": self.name}


class _Strategy(StrategyFactory):
    @property
    def strategy_name(self) -> str:
        return "demo-strategy"

    def __call__(self, request: StrategyRequest) -> Mapping[str, JsonValue]:
        payload: dict[str, JsonValue] = dict(request.base_config)
        payload.update(request.overrides)
        return payload


class _Snapshot(CatalogSnapshot):
    checksum = "abc"

    @property
    def tools(self):
        return (_Tool(),)

    def strategy(self, identifier: str) -> StrategyFactory:
        return _Strategy()


def test_catalog_protocols() -> None:
    assert isinstance(_Tool(), ToolDefinition)
    assert isinstance(_Strategy(), StrategyFactory)
    assert isinstance(_Snapshot(), CatalogSnapshot)


class _Command(CliCommand):
    @property
    def name(self) -> str:
        return "cli-demo"

    def execute(self, invocation: CliInvocation) -> int | None:
        return 0


class _CommandFactory(CliCommandFactory):
    @property
    def command_name(self) -> str:
        return "cli-demo"

    def create(self, argv: Sequence[str] | None = None) -> CliCommand:
        return _Command()


def test_cli_protocols() -> None:
    assert isinstance(_Command(), CliCommand)
    assert isinstance(_CommandFactory(), CliCommandFactory)


class _ComplianceCheck(ComplianceCheck):
    @property
    def identifier(self) -> str:
        return "compliance"

    def run(self) -> Sequence[str]:
        return ["issue"]


class _PolicyEvaluator(PolicyEvaluator):
    @property
    def policy_name(self) -> str:
        return "policy"

    def evaluate(self, payload: Mapping[str, str]) -> None:
        return None


class _Remediation(RemediationService):
    @property
    def supported_issues(self) -> Sequence[str]:
        return ("issue",)

    def apply(self, issue_identifier: str) -> bool:
        return True


def test_compliance_protocols() -> None:
    assert isinstance(_ComplianceCheck(), ComplianceCheck)
    assert isinstance(_PolicyEvaluator(), PolicyEvaluator)
    assert isinstance(_Remediation(), RemediationService)


class _Source(ConfigSource):
    name = "test"

    def load(self):
        return {}

    def describe(self) -> str:
        return "test"


class _Resolver(ConfigResolver):
    @property
    def strategy_name(self) -> str:
        return "resolver"

    def resolve(self, *sources: Mapping[str, str]) -> Mapping[str, str]:
        return {"result": "ok"}


class _Mutator(ConfigMutator):
    @property
    def description(self) -> str:
        return "mutator"

    def apply(self, data: MutableMapping[str, str]) -> None:
        data["mutated"] = "true"


def test_config_protocols() -> None:
    assert isinstance(_Source(), ConfigSource)
    assert isinstance(_Resolver(), ConfigResolver)
    target: dict[str, str] = {}
    _Mutator().apply(target)
    assert target == {"mutated": "true"}


class _ConsoleFactory(ConsoleFactory):
    @property
    def default_color(self) -> bool:
        return True

    def __call__(self, *, color: bool, emoji: bool) -> Console:
        return Console(color_system="truecolor")


class _LoggerFactory(LoggerFactory):
    @property
    def namespace(self) -> str:
        return "pyqa"

    def __call__(self, name: str):
        import logging

        return logging.getLogger(name)


class _Serializer(Serializer):
    @property
    def content_type(self) -> str:
        return "application/json"

    def dump(self, value: JsonValue) -> str:
        return "{}"

    def load(self, payload: str) -> JsonValue:
        return {"payload": payload}


def test_core_protocols() -> None:
    assert isinstance(_ConsoleFactory(), ConsoleFactory)
    assert isinstance(_LoggerFactory(), LoggerFactory)
    assert isinstance(_Serializer(), Serializer)


class _ExcludePolicy(ExcludePolicy):
    @property
    def policy_name(self) -> str:
        return "default"

    def exclusions(self):
        return ("*.py",)


class _TargetPlanner(TargetPlanner):
    @property
    def planner_name(self) -> str:
        return "planner"

    def plan(self):
        return ("src",)


class _DiscoveryStrategy(DiscoveryStrategy):
    @property
    def identifier(self) -> str:
        return "discover"

    def discover(self, config, root: Path):
        return (root / "src",)

    def __call__(self, config, root: Path):
        return self.discover(config, root)


def test_discovery_protocols() -> None:
    assert isinstance(_ExcludePolicy(), ExcludePolicy)
    assert isinstance(_TargetPlanner(), TargetPlanner)
    assert isinstance(_DiscoveryStrategy(), DiscoveryStrategy)


class _Preparer(EnvironmentPreparer):
    @property
    def preparer_name(self) -> str:
        return "preparer"

    def prepare(self) -> None:
        return None


class _RuntimeResolver(RuntimeResolver):
    @property
    def supported_tools(self) -> tuple[str, ...]:
        return ("tool",)

    def resolve(self, tool: str) -> Path:
        return Path("/bin/true")


class _WorkspaceLocator(WorkspaceLocator):
    @property
    def workspace_hint(self) -> str:
        return "workspace"

    def locate(self) -> Path:
        return Path("/")


def test_environment_protocols() -> None:
    assert isinstance(_Preparer(), EnvironmentPreparer)
    assert isinstance(_RuntimeResolver(), RuntimeResolver)
    assert isinstance(_WorkspaceLocator(), WorkspaceLocator)


class _Executor(ActionExecutor):
    @property
    def executor_name(self) -> str:
        return "executor"

    def execute(self, action_name: str) -> None:
        return None


class _Hooks(RunHooks):
    @property
    def supported_phases(self) -> Sequence[str]:
        return ("plan", "execute")

    def before_phase(self, phase: str) -> None:
        return None

    def after_phase(self, phase: str) -> None:
        return None


class _Pipeline(ExecutionPipeline):
    @property
    def pipeline_name(self) -> str:
        return "pipeline"

    def run(self, config, *, root):
        return {"config": config, "root": root}

    def plan_tools(self, config, *, root):
        return ()

    def fetch_all_tools(self, config, *, root, callback=None):
        if callback is not None:
            callback("start")
        return []


def test_orchestration_protocols() -> None:
    assert isinstance(_Executor(), ActionExecutor)
    assert isinstance(_Hooks(), RunHooks)
    assert isinstance(_Pipeline(), ExecutionPipeline)


class _Presenter(DiagnosticPresenter):
    @property
    def format_name(self) -> str:
        return "text"

    def render(self, diagnostics: Iterable[JsonValue]) -> str:
        return "rendered"


class _Advisor(AdviceProvider):
    @property
    def provider_name(self) -> str:
        return "advisor"

    def advise(self, diagnostics: Iterable[JsonValue]) -> Sequence[str]:
        return ["advice"]


def test_reporting_protocols() -> None:
    assert isinstance(_Presenter(), DiagnosticPresenter)
    assert isinstance(_Advisor(), AdviceProvider)
