"""Domain interfaces supporting the pyqa reorganisation.

Each module exposes protocols that higher-level packages will depend on.  By
centralising these contracts we can invert dependencies and allow alternative
implementations (including external plugins) to integrate without modifying the
core code base.
"""

from __future__ import annotations

from .analysis import AnnotationProvider, MessageSpan
from .catalog import CatalogSnapshot, StrategyFactory, ToolDefinition
from .cli import CliCommand, CliCommandFactory
from .compliance import ComplianceCheck, PolicyEvaluator, RemediationService
from .config import ConfigMutator, ConfigResolver, ConfigSource
from .core import ConsoleFactory, LoggerFactory, Serializer
from .discovery import DiscoveryStrategy, ExcludePolicy, TargetPlanner
from .environment import EnvironmentPreparer, RuntimeResolver, WorkspaceLocator
from .orchestration import ActionExecutor, ExecutionPipeline, RunHooks
from .reporting import AdviceProvider, DiagnosticPresenter

__all__ = [
    "AnnotationProvider",
    "MessageSpan",
    "CatalogSnapshot",
    "StrategyFactory",
    "ToolDefinition",
    "CliCommand",
    "CliCommandFactory",
    "ComplianceCheck",
    "PolicyEvaluator",
    "RemediationService",
    "ConfigMutator",
    "ConfigResolver",
    "ConfigSource",
    "ConsoleFactory",
    "LoggerFactory",
    "Serializer",
    "DiscoveryStrategy",
    "ExcludePolicy",
    "TargetPlanner",
    "EnvironmentPreparer",
    "RuntimeResolver",
    "WorkspaceLocator",
    "ActionExecutor",
    "ExecutionPipeline",
    "RunHooks",
    "AdviceProvider",
    "DiagnosticPresenter",
]
