# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Strategy definition models for tooling catalog entries."""

from __future__ import annotations

from typing import Final

from tooling_spec.catalog import model_strategy as _spec_model_strategy

StrategyConfigField = _spec_model_strategy.StrategyConfigField
StrategyDefinition = _spec_model_strategy.StrategyDefinition
StrategyImplementation = _spec_model_strategy.StrategyImplementation
StrategyMetadata = _spec_model_strategy.StrategyMetadata
StrategyType = _spec_model_strategy.StrategyType
StrategyCallable = _spec_model_strategy.StrategyCallable
normalize_strategy_type = _spec_model_strategy.normalize_strategy_type
parse_strategy_metadata = _spec_model_strategy.parse_strategy_metadata
strategy_config_mapping = _spec_model_strategy.strategy_config_mapping

__all__: Final[tuple[str, ...]] = (
    "strategy_config_mapping",
    "parse_strategy_metadata",
    "normalize_strategy_type",
    "StrategyType",
    "StrategyMetadata",
    "StrategyImplementation",
    "StrategyDefinition",
    "StrategyConfigField",
    "StrategyCallable",
)
