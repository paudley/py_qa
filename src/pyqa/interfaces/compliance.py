# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for policy/compliance subsystems."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from pyqa.core.serialization import JsonValue


@runtime_checkable
class ComplianceCheck(Protocol):
    """Perform a policy check and return collected issues."""

    @property
    @abstractmethod
    def identifier(self) -> str:
        """Return the unique identifier for the compliance check.

        Returns:
            str: Unique compliance check identifier.
        """
        raise NotImplementedError

    @abstractmethod
    def run(self) -> Sequence[str]:
        """Execute the compliance check and return human-readable issues.

        Returns:
            Sequence[str]: Human-readable issues uncovered by the check.
        """
        raise NotImplementedError


@runtime_checkable
class PolicyEvaluator(Protocol):
    """Assess policy inputs and raise or return guidance."""

    @property
    @abstractmethod
    def policy_name(self) -> str:
        """Return the policy name evaluated by the service.

        Returns:
            str: Policy name handled by the evaluator.
        """
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, payload: JsonValue) -> None:
        """Evaluate ``payload`` and raise if policy constraints are violated.

        Args:
            payload: JSON payload subjected to policy evaluation.
        """
        ...


@runtime_checkable
class RemediationService(Protocol):
    """Provide automated remediation for policy failures."""

    @property
    @abstractmethod
    def supported_issues(self) -> Sequence[str]:
        """Return the issue identifiers supported by the service.

        Returns:
            Sequence[str]: Issue identifiers eligible for remediation.
        """
        raise NotImplementedError

    @abstractmethod
    def apply(self, issue_identifier: str) -> bool:
        """Attempt remediation and report success.

        Args:
            issue_identifier: Identifier corresponding to the issue to remediate.

        Returns:
            bool: ``True`` when remediation succeeds; otherwise ``False``.
        """
        ...


@runtime_checkable
class QualityConfigSection(Protocol):
    """Expose quality enforcement configuration consumed by quality checks."""

    @property
    def checks(self) -> list[str]:
        """Return the quality checks selected for execution.

        Returns:
            list[str]: the quality checks selected for execution.
        """
        return cast(list[str], NotImplemented)

    @property
    def skip_globs(self) -> list[str]:
        """Return glob patterns ignored by quality checks.

        Returns:
            list[str]: glob patterns ignored by quality checks.
        """
        return cast(list[str], NotImplemented)

    @property
    def schema_targets(self) -> list[Path]:
        """Return schema targets requiring validation.

        Returns:
            list[Path]: schema targets requiring validation.
        """
        return cast(list[Path], NotImplemented)

    @property
    def warn_file_size(self) -> int:
        """Return the file size threshold that emits warnings.

        Returns:
            int: the file size threshold that emits warnings.
        """
        return cast(int, NotImplemented)

    @property
    def max_file_size(self) -> int:
        """Return the maximum permitted file size.

        Returns:
            int: the maximum permitted file size.
        """
        return cast(int, NotImplemented)

    @property
    def protected_branches(self) -> list[str]:
        """Return branches protected by quality enforcement.

        Returns:
            list[str]: branches protected by quality enforcement.
        """
        return cast(list[str], NotImplemented)

    @property
    def enforce_in_lint(self) -> bool:
        """Return whether quality checks run during lint commands.

        Returns:
            bool: whether quality checks run during lint commands.
        """
        return cast(bool, NotImplemented)


@runtime_checkable
class LicenseConfig(Protocol):
    """Expose licensing configuration toggles used by compliance checks."""

    @property
    def spdx(self) -> str | None:
        """Return the primary SPDX identifier.

        Returns:
            str | None: the primary SPDX identifier.
        """
        return cast(str | None, NotImplemented)

    @property
    def notice(self) -> str | None:
        """Return the copyright notice text.

        Returns:
            str | None: the copyright notice text.
        """
        return cast(str | None, NotImplemented)

    @property
    def copyright(self) -> str | None:
        """Return the copyright holder string.

        Returns:
            str | None: the copyright holder string.
        """
        return cast(str | None, NotImplemented)

    @property
    def year(self) -> str | None:
        """Return the copyright year range.

        Returns:
            str | None: the copyright year range.
        """
        return cast(str | None, NotImplemented)

    @property
    def require_spdx(self) -> bool:
        """Return whether SPDX identifiers are mandatory.

        Returns:
            bool: whether SPDX identifiers are mandatory.
        """
        return cast(bool, NotImplemented)

    @property
    def require_notice(self) -> bool:
        """Return whether notices are required.

        Returns:
            bool: whether notices are required.
        """
        return cast(bool, NotImplemented)

    @property
    def allow_alternate_spdx(self) -> list[str]:
        """Return alternate SPDX identifiers permitted by policy.

        Returns:
            list[str]: alternate SPDX identifiers permitted by policy.
        """
        return cast(list[str], NotImplemented)

    @property
    def exceptions(self) -> list[str]:
        """Return file-level exceptions to licensing rules.

        Returns:
            list[str]: file-level exceptions to licensing rules.
        """
        return cast(list[str], NotImplemented)
