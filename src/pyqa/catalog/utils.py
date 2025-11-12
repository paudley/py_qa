# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Utility helpers for validating and normalising catalog JSON structures."""

from __future__ import annotations

from tooling_spec.catalog import utils as _spec_utils

expect_string = _spec_utils.expect_string
optional_string = _spec_utils.optional_string
optional_bool = _spec_utils.optional_bool
string_array = _spec_utils.string_array
expect_mapping = _spec_utils.expect_mapping
freeze_json_mapping = _spec_utils.freeze_json_mapping
freeze_json_value = _spec_utils.freeze_json_value
optional_number = _spec_utils.optional_number
string_mapping = _spec_utils.string_mapping
thaw_json_value = _spec_utils.thaw_json_value

__all__ = (
    "optional_number",
    "optional_bool",
    "optional_string",
    "expect_string",
    "string_array",
    "string_mapping",
    "expect_mapping",
    "freeze_json_mapping",
    "freeze_json_value",
    "thaw_json_value",
)
