# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Runtime configuration models for tooling catalog entries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, TypeAlias, cast

from .errors import CatalogIntegrityError
from .types import JSONValue
from .utils import (
    expect_mapping,
    expect_string,
    freeze_json_mapping,
    optional_string,
    string_array,
    string_mapping,
)

RuntimeType: TypeAlias = Literal["python", "npm", "binary", "go", "lua", "perl", "rust"]
SUPPORTED_RUNTIME_TYPES: Final[tuple[RuntimeType, ...]] = (
    "python",
    "npm",
    "binary",
    "go",
    "lua",
    "perl",
    "rust",
)


def normalize_runtime_type(value: JSONValue | None, *, context: str) -> RuntimeType:
    """Return the validated runtime kind referenced by an option mapping.

    Args:
        value: Raw type value sourced from catalog metadata.
        context: Human-readable context used in error messages.

    Returns:
        RuntimeType: Known runtime type understood by the execution layer.

    Raises:
        CatalogIntegrityError: If the type value is missing or not supported.

    """

    runtime_value = expect_string(value, key="type", context=context)
    if runtime_value not in SUPPORTED_RUNTIME_TYPES:
        raise CatalogIntegrityError(f"{context}: runtime type '{runtime_value}' is not supported")
    return cast(RuntimeType, runtime_value)


@dataclass(frozen=True, slots=True)
class RuntimeInstallDefinition:
    """Declarative installation strategy for tool runtimes."""

    strategy: str
    config: Mapping[str, JSONValue]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> RuntimeInstallDefinition:
        """Create an installation definition from JSON data.

        Args:
            data: Mapping describing the installation instructions.
            context: Human-readable context used in error messages.

        Returns:
            RuntimeInstallDefinition: Frozen installation metadata.

        Raises:
            CatalogIntegrityError: If required fields are missing or invalid.

        """

        strategy_value = expect_string(data.get("strategy"), key="strategy", context=context)
        config_data = data.get("config")
        config_mapping: Mapping[str, JSONValue]
        if isinstance(config_data, Mapping):
            frozen_config = expect_mapping(config_data, key="config", context=context)
            config_mapping = freeze_json_mapping(frozen_config, context=f"{context}.config")
        else:
            config_mapping = MappingProxyType({})
        return RuntimeInstallDefinition(strategy=strategy_value, config=config_mapping)


@dataclass(frozen=True, slots=True)
class RuntimeDefinition:
    """Runtime metadata required to execute a tool."""

    kind: RuntimeType
    package: str | None
    min_version: str | None
    max_version: str | None
    version_command: tuple[str, ...]
    binaries: Mapping[str, str]
    install: RuntimeInstallDefinition | None

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> RuntimeDefinition:
        """Create a ``RuntimeDefinition`` from JSON data.

        Args:
            data: Mapping describing runtime configuration.
            context: Human-readable context used in error messages.

        Returns:
            RuntimeDefinition: Frozen runtime metadata instance.

        Raises:
            CatalogIntegrityError: If required runtime fields are missing or invalid.

        """

        kind_value = normalize_runtime_type(data.get("type"), context=context)
        package_value = optional_string(data.get("package"), key="package", context=context)
        min_version_value = optional_string(
            data.get("minVersion"),
            key="minVersion",
            context=context,
        )
        max_version_value = optional_string(
            data.get("maxVersion"),
            key="maxVersion",
            context=context,
        )
        version_command_value = string_array(
            data.get("versionCommand"),
            key="versionCommand",
            context=context,
        )
        binaries_value = string_mapping(data.get("binaries"), key="binaries", context=context)
        install_data = data.get("install")
        install_value = (
            RuntimeInstallDefinition.from_mapping(
                expect_mapping(install_data, key="install", context=context),
                context=f"{context}.install",
            )
            if isinstance(install_data, Mapping)
            else None
        )
        return RuntimeDefinition(
            kind=kind_value,
            package=package_value,
            min_version=min_version_value,
            max_version=max_version_value,
            version_command=version_command_value,
            binaries=binaries_value,
            install=install_value,
        )


__all__: Final[tuple[str, ...]] = (
    "RuntimeDefinition",
    "RuntimeInstallDefinition",
    "RuntimeType",
    "SUPPORTED_RUNTIME_TYPES",
    "normalize_runtime_type",
)
