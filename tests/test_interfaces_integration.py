from __future__ import annotations

from pathlib import Path

from pyqa.analysis.bootstrap import register_analysis_services
from pyqa.cli.commands.lint.params import LintOutputArtifacts
from pyqa.cli.commands.lint.reporting import handle_reporting
from pyqa.config import Config
from pyqa.core.models import RunResult
from pyqa.core.runtime.di import ServiceContainer
from pyqa.interfaces.analysis import AnnotationProvider, ContextResolver
from pyqa.orchestration.orchestrator import Orchestrator, OrchestratorOverrides
from pyqa.tools.registry import ToolRegistry


class _StubAnnotationProvider:
    def __init__(self) -> None:
        self.annotate_calls = 0

    def annotate_run(self, result: RunResult) -> dict[int, object]:
        self.annotate_calls += 1
        return {}

    def message_spans(self, message: str):
        return ()

    def message_signature(self, message: str):
        return ()


class _StubDiscovery:
    def run(self, config, root):  # noqa: D401, ANN001
        return []

    __call__ = run


def test_orchestrator_resolves_annotation_provider_from_services() -> None:
    registry = ToolRegistry()
    discovery = _StubDiscovery()
    container = ServiceContainer()
    provider = _StubAnnotationProvider()
    container.register("annotation_provider", lambda _: provider)

    orchestrator = Orchestrator(
        registry=registry,
        discovery=discovery,
        overrides=OrchestratorOverrides(services=container),
    )

    assert orchestrator._annotation_provider is provider  # type: ignore[attr-defined]


def test_orchestrator_falls_back_to_default_provider() -> None:
    registry = ToolRegistry()
    discovery = _StubDiscovery()
    orchestrator = Orchestrator(registry=registry, discovery=discovery)

    assert isinstance(orchestrator._annotation_provider, AnnotationProvider)  # type: ignore[attr-defined]


def test_analysis_services_register_interfaces() -> None:
    container = ServiceContainer()
    register_analysis_services(container)

    provider = container.resolve("annotation_provider")
    resolver = container.resolve("context_resolver")

    assert isinstance(provider, AnnotationProvider)
    assert isinstance(resolver, ContextResolver)


def test_handle_reporting_uses_injected_annotation_provider(tmp_path: Path) -> None:
    provider = _StubAnnotationProvider()
    result = RunResult(root=tmp_path, files=[], outcomes=[], tool_versions={})
    config = Config()
    artifacts = LintOutputArtifacts(report_json=None, sarif_out=None, pr_summary_out=None)

    handle_reporting(result, config, artifacts, annotation_provider=provider, logger=None)

    assert provider.annotate_calls == 1
