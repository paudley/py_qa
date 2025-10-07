# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Interfaces for policy/compliance subsystems."""

# pylint: disable=too-few-public-methods -- Protocol definitions intentionally expose minimal method surfaces.

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class ComplianceCheck(Protocol):
    """Perform a policy check and return collected issues."""

    def run(self) -> Sequence[str]:
        """Execute the compliance check and return human-readable issues."""
        raise NotImplementedError


@runtime_checkable
class PolicyEvaluator(Protocol):
    """Assess policy inputs and raise or return guidance."""

    def evaluate(self, payload: object) -> None:
        """Evaluate ``payload`` and raise if policy constraints are violated."""
        raise NotImplementedError


@runtime_checkable
class RemediationService(Protocol):
    """Provide automated remediation for policy failures."""

    def apply(self, issue_identifier: str) -> bool:
        """Attempt remediation and report success."""
        raise NotImplementedError
