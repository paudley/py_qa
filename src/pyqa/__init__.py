# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""pyqa – modular lint orchestration."""

from __future__ import annotations

from importlib import metadata

from .config import (
    Config,
    ConfigError,
    DedupeConfig,
    ExecutionConfig,
    FileDiscoveryConfig,
    OutputConfig,
)
from .config_loader import ConfigLoader, generate_config_schema, load_config
from .discovery import build_default_discovery
from .execution.orchestrator import Orchestrator, OrchestratorHooks
from .tools.builtins import register_builtin_tools
from .tools.registry import DEFAULT_REGISTRY

__all__ = [
    "Config",
    "ConfigError",
    "DedupeConfig",
    "ExecutionConfig",
    "FileDiscoveryConfig",
    "OutputConfig",
    "ConfigLoader",
    "generate_config_schema",
    "load_config",
    "Orchestrator",
    "OrchestratorHooks",
    "build_default_discovery",
]


def __getattr__(name: str) -> str:
    if name == "__version__":
        try:
            return metadata.version("py-qa")
        except metadata.PackageNotFoundError:  # pragma: no cover - local builds
            return "0.0.0"
    raise AttributeError(name)


if len(DEFAULT_REGISTRY) == 0:  # pragma: no cover - import side effect
    register_builtin_tools(DEFAULT_REGISTRY)
