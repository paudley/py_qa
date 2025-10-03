# SPDX-License-Identifier: MIT
"""pyqa – modular lint orchestration."""

from __future__ import annotations

from importlib import import_module, metadata
from typing import TYPE_CHECKING, Any, Final

_ExportTarget = tuple[str, str]

_EXPORT_NAME_TO_TARGET: Final[dict[str, _ExportTarget]] = {
    "Config": ("pyqa.config", "Config"),
    "ConfigError": ("pyqa.config", "ConfigError"),
    "ConfigLoader": ("pyqa.config_loader", "ConfigLoader"),
    "DedupeConfig": ("pyqa.config", "DedupeConfig"),
    "ExecutionConfig": ("pyqa.config", "ExecutionConfig"),
    "FileDiscoveryConfig": ("pyqa.config", "FileDiscoveryConfig"),
    "Orchestrator": ("pyqa.execution.orchestrator", "Orchestrator"),
    "OrchestratorHooks": ("pyqa.execution.orchestrator", "OrchestratorHooks"),
    "OutputConfig": ("pyqa.config", "OutputConfig"),
    "SecurityScanner": ("pyqa.security", "SecurityScanner"),
    "build_default_discovery": ("pyqa.discovery", "build_default_discovery"),
    "generate_config_schema": ("pyqa.config_loader", "generate_config_schema"),
    "load_config": ("pyqa.config_loader", "load_config"),
}

_VERSION_ATTRIBUTE: Final[str] = "__version__"

__all__ = tuple(_EXPORT_NAME_TO_TARGET)

if TYPE_CHECKING:  # pragma: no cover - import hints for static analysis only
    from pyqa.config import Config, ConfigError, DedupeConfig, ExecutionConfig, FileDiscoveryConfig, OutputConfig
    from pyqa.config_loader import ConfigLoader, generate_config_schema, load_config
    from pyqa.discovery import build_default_discovery
    from pyqa.execution.orchestrator import Orchestrator, OrchestratorHooks
    from pyqa.security import SecurityScanner


def __getattr__(name: str) -> Any:
    """Return lazily imported exports for the top-level ``pyqa`` package.

    Args:
        name: Attribute requested by the caller.

    Returns:
        Any: The requested attribute sourced from the appropriate submodule.

    Raises:
        AttributeError: If ``name`` is not a recognised export.

    """

    if name == _VERSION_ATTRIBUTE:
        try:
            return metadata.version("py-qa")
        except metadata.PackageNotFoundError:
            return "0.0.0"

    target = _EXPORT_NAME_TO_TARGET.get(name)
    if target is None:
        raise AttributeError(name) from None
    module_name, attribute = target
    module = import_module(module_name)
    value = getattr(module, attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return attributes exposed from the top-level package."""

    return [*_EXPORT_NAME_TO_TARGET, _VERSION_ATTRIBUTE]
