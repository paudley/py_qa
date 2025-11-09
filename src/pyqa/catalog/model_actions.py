# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Action metadata models for tooling catalog entries."""

from __future__ import annotations

from pyqa.interfaces.core import JsonValue
from tooling_spec.catalog.errors import CatalogIntegrityError as SpecCatalogIntegrityError
from tooling_spec.catalog.model_actions import ActionDefinition, ActionExecution
from tooling_spec.catalog.model_actions import actions_array as _spec_actions_array

from .errors import CatalogIntegrityError

__all__ = ("ActionDefinition", "ActionExecution", "actions_array")


def actions_array(
    value: JsonValue | None,
    *,
    key: str,
    context: str,
) -> tuple[ActionDefinition, ...]:
    """Validate an array of catalog action definitions.

    Args:
        value: Raw JSON payload describing the catalog actions.
        key: Name of the catalog key being parsed.
        context: Human-readable context used when raising validation errors.

    Returns:
        tuple[ActionDefinition, ...]: Normalised action definitions derived from ``value``.

    Raises:
        CatalogIntegrityError: If ``value`` cannot be interpreted as a sequence of actions.
    """

    try:
        return _spec_actions_array(value, key=key, context=context)
    except SpecCatalogIntegrityError as exc:  # pragma: no cover - defensive for upstream schema
        raise CatalogIntegrityError(str(exc)) from exc
