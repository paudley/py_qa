# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Diagnostics and suppression metadata for tooling catalog entries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .types import JSONValue
from .utils import expect_mapping, string_array, string_mapping


@dataclass(frozen=True, slots=True)
class DiagnosticsDefinition:
    """Diagnostic post-processing configuration."""

    dedupe: Mapping[str, str]
    severity_mapping: Mapping[str, str]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> DiagnosticsDefinition:
        """Create a ``DiagnosticsDefinition`` from JSON data.

        Args:
            data: Mapping containing diagnostics metadata.
            context: Human-readable context used in error messages.

        Returns:
            DiagnosticsDefinition: Frozen diagnostics configuration.

        Raises:
            CatalogIntegrityError: If required diagnostics metadata is missing or invalid.

        """

        dedupe_value = string_mapping(data.get("dedupe"), key="dedupe", context=context)
        severity_value = string_mapping(
            data.get("severityMapping"),
            key="severityMapping",
            context=context,
        )
        return DiagnosticsDefinition(dedupe=dedupe_value, severity_mapping=severity_value)


@dataclass(frozen=True, slots=True)
class SuppressionsDefinition:
    """Suppressions applied to diagnostics emitted by a tool."""

    tests: tuple[str, ...]
    general: tuple[str, ...]
    duplicates: tuple[str, ...]

    @staticmethod
    def from_mapping(data: Mapping[str, JSONValue], *, context: str) -> SuppressionsDefinition:
        """Create a ``SuppressionsDefinition`` from JSON data.

        Args:
            data: Mapping containing suppression settings.
            context: Human-readable context used in error messages.

        Returns:
            SuppressionsDefinition: Frozen suppression configuration.

        Raises:
            CatalogIntegrityError: If suppression metadata is invalid.

        """

        tests_value = string_array(data.get("tests"), key="tests", context=context)
        general_value = string_array(data.get("general"), key="general", context=context)
        duplicates_value = string_array(data.get("duplicates"), key="duplicates", context=context)
        return SuppressionsDefinition(
            tests=tests_value,
            general=general_value,
            duplicates=duplicates_value,
        )


@dataclass(frozen=True, slots=True)
class DiagnosticsBundle:
    """Container for diagnostics and suppression metadata."""

    diagnostics: DiagnosticsDefinition | None
    suppressions: SuppressionsDefinition | None

    @staticmethod
    def from_tool_mapping(data: Mapping[str, JSONValue], *, context: str) -> DiagnosticsBundle:
        """Create a ``DiagnosticsBundle`` from tool metadata.

        Args:
            data: Mapping containing diagnostics and suppression metadata.
            context: Human-readable context used in error messages.

        Returns:
            DiagnosticsBundle: Frozen bundle containing optional definitions.

        Raises:
            CatalogIntegrityError: If diagnostics or suppression entries are invalid.

        """

        diagnostics_data = data.get("diagnostics")
        diagnostics_value = (
            DiagnosticsDefinition.from_mapping(
                expect_mapping(diagnostics_data, key="diagnostics", context=context),
                context=f"{context}.diagnostics",
            )
            if isinstance(diagnostics_data, Mapping)
            else None
        )
        suppressions_data = data.get("suppressions")
        suppressions_value = (
            SuppressionsDefinition.from_mapping(
                expect_mapping(suppressions_data, key="suppressions", context=context),
                context=f"{context}.suppressions",
            )
            if isinstance(suppressions_data, Mapping)
            else None
        )
        return DiagnosticsBundle(
            diagnostics=diagnostics_value,
            suppressions=suppressions_value,
        )


__all__ = [
    "DiagnosticsBundle",
    "DiagnosticsDefinition",
    "SuppressionsDefinition",
]
