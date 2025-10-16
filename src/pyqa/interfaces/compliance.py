# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for policy/compliance subsystems."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pyqa.core.serialization import JsonValue


@runtime_checkable
class ComplianceCheck(Protocol):
    """Perform a policy check and return collected issues."""

    @property
    @abstractmethod
    def identifier(self) -> str:
        """Return the unique identifier for the compliance check.

        Returns:
            str: Unique identifier describing the compliance check.
        """
        raise NotImplementedError

    @abstractmethod
    def run(self) -> Sequence[str]:
        """Execute the compliance check and return human-readable issues.

        Returns:
            Sequence[str]: Collection of human-readable issues uncovered by the check.
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
            str: Name of the policy handled by the evaluator.
        """
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, payload: JsonValue) -> None:
        """Evaluate ``payload`` and raise if policy constraints are violated.

        Args:
            payload: JSON payload subjected to policy evaluation.
        """
        raise NotImplementedError


@runtime_checkable
class RemediationService(Protocol):
    """Provide automated remediation for policy failures."""

    @property
    @abstractmethod
    def supported_issues(self) -> Sequence[str]:
        """Return the issue identifiers supported by the service.

        Returns:
            Sequence[str]: Collection of issue identifiers eligible for remediation.
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
        raise NotImplementedError
