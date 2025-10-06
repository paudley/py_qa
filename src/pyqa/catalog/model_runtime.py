# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Runtime configuration models for tooling catalog entries."""

from __future__ import annotations

from typing import Final

from tooling_spec.catalog import model_runtime as _spec_model_runtime

RuntimeDefinition = _spec_model_runtime.RuntimeDefinition
RuntimeInstallDefinition = _spec_model_runtime.RuntimeInstallDefinition
RuntimeType = _spec_model_runtime.RuntimeType
SUPPORTED_RUNTIME_TYPES = _spec_model_runtime.SUPPORTED_RUNTIME_TYPES
normalize_runtime_type = _spec_model_runtime.normalize_runtime_type

__all__: Final[tuple[str, ...]] = (
    "SUPPORTED_RUNTIME_TYPES",
    "normalize_runtime_type",
    "RuntimeDefinition",
    "RuntimeInstallDefinition",
    "RuntimeType",
)
