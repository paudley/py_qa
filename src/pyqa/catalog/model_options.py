# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Option metadata models for tooling catalog entries."""

from __future__ import annotations

from typing import Final

from tooling_spec.catalog import model_options as _spec_model_options

CliOptionMetadata = _spec_model_options.CliOptionMetadata
OptionDefinition = _spec_model_options.OptionDefinition
OptionDocumentationBundle = _spec_model_options.OptionDocumentationBundle
OptionGroupDefinition = _spec_model_options.OptionGroupDefinition
OptionType = _spec_model_options.OptionType
normalize_option_type = _spec_model_options.normalize_option_type
options_array = _spec_model_options.options_array

__all__: Final[tuple[str, ...]] = (
    "options_array",
    "normalize_option_type",
    "OptionType",
    "CliOptionMetadata",
    "OptionDefinition",
    "OptionGroupDefinition",
    "OptionDocumentationBundle",
)
