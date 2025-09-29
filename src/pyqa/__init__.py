# SPDX-License-Identifier: MIT
"""pyqa – modular lint orchestration."""

from __future__ import annotations

from importlib import import_module, metadata
from typing import Any

__all__ = [
    "Config",
    "ConfigError",
    "ConfigLoader",
    "DedupeConfig",
    "ExecutionConfig",
    "FileDiscoveryConfig",
    "OutputConfig",
    "Orchestrator",
    "OrchestratorHooks",
    "SecurityScanner",
    "build_default_discovery",
    "generate_config_schema",
    "load_config",
]


def __getattr__(name: str) -> Any:
    if name == "__version__":
        try:
            return metadata.version("py-qa")
        except metadata.PackageNotFoundError:
            return "0.0.0"

    module_map = {
        "Config": ("pyqa.config", "Config"),
        "ConfigError": ("pyqa.config", "ConfigError"),
        "DedupeConfig": ("pyqa.config", "DedupeConfig"),
        "ExecutionConfig": ("pyqa.config", "ExecutionConfig"),
        "FileDiscoveryConfig": ("pyqa.config", "FileDiscoveryConfig"),
        "OutputConfig": ("pyqa.config", "OutputConfig"),
        "ConfigLoader": ("pyqa.config_loader", "ConfigLoader"),
        "generate_config_schema": ("pyqa.config_loader", "generate_config_schema"),
        "load_config": ("pyqa.config_loader", "load_config"),
        "build_default_discovery": ("pyqa.discovery", "build_default_discovery"),
        "Orchestrator": ("pyqa.execution.orchestrator", "Orchestrator"),
        "OrchestratorHooks": ("pyqa.execution.orchestrator", "OrchestratorHooks"),
        "SecurityScanner": ("pyqa.security", "SecurityScanner"),
    }

    target = module_map.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    module = import_module(module_name)
    value = getattr(module, attribute)
    globals()[name] = value
    return value
