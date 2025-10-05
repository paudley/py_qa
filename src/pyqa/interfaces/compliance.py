"""Interfaces for policy/compliance subsystems."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from collections.abc import Sequence


@runtime_checkable
class ComplianceCheck(Protocol):
    """Perform a policy check and return collected issues."""

    def run(self) -> Sequence[str]:
        """Execute the compliance check and return human-readable issues."""
        ...


@runtime_checkable
class PolicyEvaluator(Protocol):
    """Assess policy inputs and raise or return guidance."""

    def evaluate(self, payload: object) -> None:
        """Evaluate ``payload`` and raise if policy constraints are violated."""
        ...


@runtime_checkable
class RemediationService(Protocol):
    """Provide automated remediation for policy failures."""

    def apply(self, issue_identifier: str) -> bool:
        """Attempt remediation and report success."""
        ...
