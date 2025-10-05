# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, MutableMapping

from pyqa.interfaces.analysis import AnnotationProvider, MessageSpan
from pyqa.interfaces.catalog import CatalogSnapshot, StrategyFactory, ToolDefinition
from pyqa.interfaces.cli import CliCommand, CliCommandFactory
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


class _AnnotationProvider:
    def message_spans(self, message: str):
        return [_Span()]


def test_annotation_provider_protocol() -> None:
    assert isinstance(_Span(), MessageSpan)
    assert isinstance(_AnnotationProvider(), AnnotationProvider)


class _Tool(ToolDefinition):
    name = "demo"
    phase = "lint"
    languages = ("python",)

    def to_dict(self) -> Mapping[str, object]:
        return {"name": self.name}


class _Strategy(StrategyFactory):
    def __call__(self, **config):
        return config


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
    def __call__(self, *args, **kwargs):
        return 0


class _CommandFactory(CliCommandFactory):
    def create(self, argv=None):
        return _Command()


def test_cli_protocols() -> None:
    assert isinstance(_Command(), CliCommand)
    assert isinstance(_CommandFactory(), CliCommandFactory)


class _ComplianceCheck(ComplianceCheck):
    def run(self):
        return ["issue"]


class _PolicyEvaluator(PolicyEvaluator):
    def evaluate(self, payload: object) -> None:
        return None


class _Remediation(RemediationService):
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
    def resolve(self, *sources: Mapping[str, object]):
        return {}


class _Mutator(ConfigMutator):
    def apply(self, data: MutableMapping[str, object]) -> None:
        data["mutated"] = True


def test_config_protocols() -> None:
    assert isinstance(_Source(), ConfigSource)
    assert isinstance(_Resolver(), ConfigResolver)
    target: dict[str, object] = {}
    _Mutator().apply(target)
    assert target == {"mutated": True}


class _ConsoleFactory(ConsoleFactory):
    def __call__(self, *, color: bool, emoji: bool):
        return object()


class _LoggerFactory(LoggerFactory):
    def __call__(self, name: str):
        import logging

        return logging.getLogger(name)


class _Serializer(Serializer):
    def dump(self, value):
        return "{}"

    def load(self, payload: str):
        return {}


def test_core_protocols() -> None:
    assert isinstance(_ConsoleFactory(), ConsoleFactory)
    assert isinstance(_LoggerFactory(), LoggerFactory)
    assert isinstance(_Serializer(), Serializer)


class _ExcludePolicy(ExcludePolicy):
    def exclusions(self):
        return ("*.py",)


class _TargetPlanner(TargetPlanner):
    def plan(self):
        return ("src",)


class _DiscoveryStrategy(DiscoveryStrategy):
    def build(self):
        return _TargetPlanner(), _ExcludePolicy()


def test_discovery_protocols() -> None:
    assert isinstance(_ExcludePolicy(), ExcludePolicy)
    assert isinstance(_TargetPlanner(), TargetPlanner)
    assert isinstance(_DiscoveryStrategy(), DiscoveryStrategy)


class _Preparer(EnvironmentPreparer):
    def prepare(self) -> None:
        return None


class _RuntimeResolver(RuntimeResolver):
    def resolve(self, tool: str) -> Path:
        return Path("/bin/true")


class _WorkspaceLocator(WorkspaceLocator):
    def locate(self) -> Path:
        return Path("/")


def test_environment_protocols() -> None:
    assert isinstance(_Preparer(), EnvironmentPreparer)
    assert isinstance(_RuntimeResolver(), RuntimeResolver)
    assert isinstance(_WorkspaceLocator(), WorkspaceLocator)


class _Executor(ActionExecutor):
    def execute(self, action_name: str) -> None:
        return None


class _Hooks(RunHooks):
    def before_phase(self, phase: str) -> None:
        return None

    def after_phase(self, phase: str) -> None:
        return None


class _Pipeline(ExecutionPipeline):
    def run(self, hooks: RunHooks | None = None) -> None:
        return None


def test_orchestration_protocols() -> None:
    assert isinstance(_Executor(), ActionExecutor)
    assert isinstance(_Hooks(), RunHooks)
    assert isinstance(_Pipeline(), ExecutionPipeline)


class _Presenter(DiagnosticPresenter):
    def render(self, diagnostics: Iterable[object]) -> str:
        return "rendered"


class _Advisor(AdviceProvider):
    def advise(self, diagnostics: Iterable[object]):
        return ["advice"]


def test_reporting_protocols() -> None:
    assert isinstance(_Presenter(), DiagnosticPresenter)
    assert isinstance(_Advisor(), AdviceProvider)

