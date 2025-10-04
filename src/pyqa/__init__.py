# SPDX-License-Identifier: MIT
"""pyqa – modular lint orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module, metadata
from typing import TYPE_CHECKING, Final, cast


@dataclass(frozen=True, slots=True)
class ExportTarget:
    """Describe a lazily imported symbol exposed from the top-level package."""

    module: str
    attribute: str


_EXPORT_NAME_TO_TARGET: Final[dict[str, ExportTarget]] = {
    "Config": ExportTarget("pyqa.config", "Config"),
    "ConfigError": ExportTarget("pyqa.config", "ConfigError"),
    "ConfigLoader": ExportTarget("pyqa.config_loader", "ConfigLoader"),
    "DedupeConfig": ExportTarget("pyqa.config", "DedupeConfig"),
    "ExecutionConfig": ExportTarget("pyqa.config", "ExecutionConfig"),
    "FileDiscoveryConfig": ExportTarget("pyqa.config", "FileDiscoveryConfig"),
    "Orchestrator": ExportTarget("pyqa.execution.orchestrator", "Orchestrator"),
    "OrchestratorHooks": ExportTarget("pyqa.execution.orchestrator", "OrchestratorHooks"),
    "OutputConfig": ExportTarget("pyqa.config", "OutputConfig"),
    "SecurityScanner": ExportTarget("pyqa.security", "SecurityScanner"),
    "build_default_discovery": ExportTarget("pyqa.discovery", "build_default_discovery"),
    "generate_config_schema": ExportTarget("pyqa.config_loader", "generate_config_schema"),
    "load_config": ExportTarget("pyqa.config_loader", "load_config"),
}

_VERSION_ATTRIBUTE: Final[str] = "__version__"

__all__ = [
    "Config",
    "ConfigError",
    "ConfigLoader",
    "DedupeConfig",
    "ExecutionConfig",
    "FileDiscoveryConfig",
    "Orchestrator",
    "OrchestratorHooks",
    "OutputConfig",
    "SecurityScanner",
    "build_default_discovery",
    "generate_config_schema",
    "load_config",
]

if TYPE_CHECKING:  # pragma: no cover - import hints for static analysis only
    from pyqa.config import (
        Config,
        ConfigError,
        DedupeConfig,
        ExecutionConfig,
        FileDiscoveryConfig,
        OutputConfig,
    )
    from pyqa.config_loader import ConfigLoader, generate_config_schema, load_config
    from pyqa.discovery import build_default_discovery
    from pyqa.execution.orchestrator import Orchestrator, OrchestratorHooks
    from pyqa.security import SecurityScanner

    ExportedCallable = Callable[..., object]
    ExportedValue = (
        str
        | Config
        | ConfigError
        | ConfigLoader
        | DedupeConfig
        | ExecutionConfig
        | FileDiscoveryConfig
        | Orchestrator
        | OrchestratorHooks
        | OutputConfig
        | SecurityScanner
        | ExportedCallable
        | Mapping[str, object]
    )
    _TYPECHECK_EXPORTS = (
        generate_config_schema,
        load_config,
        build_default_discovery,
    )
else:  # pragma: no cover - runtime fallback uses ``object`` for short-circuit typing
    ExportedValue = object


def __getattr__(name: str) -> ExportedValue:
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
    module = import_module(target.module)
    value = getattr(module, target.attribute)
    globals()[name] = value
    return cast(ExportedValue, value)


def __dir__() -> list[str]:
    """Return attributes exposed from the top-level package.

    Returns:
        list[str]: Exported attribute names including the version sentinel.

    """

    return [*__all__, _VERSION_ATTRIBUTE]
