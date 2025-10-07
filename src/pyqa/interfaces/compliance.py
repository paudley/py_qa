# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for policy/compliance subsystems."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class ComplianceCheck(Protocol):
    """Perform a policy check and return collected issues."""

    @property
    def identifier(self) -> str:
        """Return the unique identifier for the compliance check."""
        raise NotImplementedError("ComplianceCheck.identifier must be implemented")

    def run(self) -> Sequence[str]:
        """Execute the compliance check and return human-readable issues."""
        raise NotImplementedError


@runtime_checkable
class PolicyEvaluator(Protocol):
    """Assess policy inputs and raise or return guidance."""

    @property
    def policy_name(self) -> str:
        """Return the policy name evaluated by the service."""
        raise NotImplementedError("PolicyEvaluator.policy_name must be implemented")

    def evaluate(self, payload: object) -> None:
        """Evaluate ``payload`` and raise if policy constraints are violated."""
        raise NotImplementedError


@runtime_checkable
class RemediationService(Protocol):
    """Provide automated remediation for policy failures."""

    @property
    def supported_issues(self) -> Sequence[str]:
        """Return issue identifiers supported by the service."""
        raise NotImplementedError("RemediationService.supported_issues must be implemented")

    def apply(self, issue_identifier: str) -> bool:
        """Attempt remediation and report success."""
        raise NotImplementedError
