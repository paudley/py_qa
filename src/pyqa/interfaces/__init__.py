# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Domain interfaces supporting the pyqa reorganisation."""

from __future__ import annotations

from .analysis import AnnotationProvider, MessageSpan
from .catalog import CatalogSnapshot, StrategyFactory, ToolDefinition
from .cli import CliCommand, CliCommandFactory
from .compliance import ComplianceCheck, PolicyEvaluator, RemediationService
from .config import ConfigMutator, ConfigResolver, ConfigSource
from .core import ConsoleFactory, LoggerFactory, Serializer
from .diagnostics import DiagnosticPipeline
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
    "DiagnosticPipeline",
    "DiagnosticPresenter",
]
