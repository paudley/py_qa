# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Type aliases describing configuration payload structures."""

from collections.abc import Mapping, MutableMapping, Sequence
from typing import TypeAlias

ConfigPrimitive: TypeAlias = str | int | float | bool | None
ConfigValue: TypeAlias = ConfigPrimitive | Sequence["ConfigValue"] | Mapping[str, "ConfigValue"]
ConfigFragment: TypeAlias = Mapping[str, ConfigValue]
MutableConfigFragment: TypeAlias = MutableMapping[str, ConfigValue]

__all__ = [
    "ConfigPrimitive",
    "ConfigValue",
    "ConfigFragment",
    "MutableConfigFragment",
]
