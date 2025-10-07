# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Domain interfaces supporting the pyqa reorganisation."""

from __future__ import annotations

from .analysis import AnnotationProvider, MessageSpan
from .catalog import CatalogSnapshot, StrategyFactory, ToolDefinition
from .cli import CliCommand, CliCommandFactory
from .compliance import ComplianceCheck, PolicyEvaluator, RemediationService
from .config import ConfigLoader, ConfigMutator, ConfigResolver, ConfigSource
from .core import AnsiFormatter, ConsoleFactory, ConsoleManager, LoggerFactory, Serializer
from .diagnostics import DiagnosticPipeline
from .discovery import DiscoveryStrategy, ExcludePolicy, TargetPlanner
from .environment import (
    EnvironmentInspector,
    EnvironmentPreparer,
    RuntimeResolver,
    VirtualEnvDetector,
    WorkspaceLocator,
)
from .orchestration import ActionExecutor, ExecutionPipeline, RunHooks
from .reporting import AdviceProvider, DiagnosticPresenter
from .tooling import Installer, RuntimeBootstrapper

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
    "ConfigLoader",
    "ConfigMutator",
    "ConfigResolver",
    "ConfigSource",
    "AnsiFormatter",
    "ConsoleFactory",
    "ConsoleManager",
    "LoggerFactory",
    "Serializer",
    "DiscoveryStrategy",
    "ExcludePolicy",
    "TargetPlanner",
    "EnvironmentInspector",
    "EnvironmentPreparer",
    "RuntimeResolver",
    "VirtualEnvDetector",
    "WorkspaceLocator",
    "ActionExecutor",
    "ExecutionPipeline",
    "RunHooks",
    "AdviceProvider",
    "DiagnosticPipeline",
    "DiagnosticPresenter",
    "Installer",
    "RuntimeBootstrapper",
]
