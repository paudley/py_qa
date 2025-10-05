# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Concrete configuration sources (defaults, TOML, pyproject)."""

from __future__ import annotations

import copy
import os
import tomllib
from collections.abc import Iterable, Mapping, MutableMapping
from pathlib import Path
from typing import Any, Final

from ...config import Config, ConfigError
from ...config_utils import _deep_merge, _expand_env, _normalise_pyproject_payload
from ...interfaces.config import ConfigSource

DEFAULT_INCLUDE_KEY: Final[str] = "include"
PYPROJECT_TOOL_KEY: Final[str] = "tool"
PYPROJECT_SECTION_KEY: Final[str] = "pyqa"
CONFIG_KEY: Final[str] = "config"

_TOML_CACHE: dict[tuple[Path, int], Mapping[str, Any]] = {}


class DefaultConfigSource(ConfigSource):
    """Return the built-in defaults as a configuration fragment."""

    name = "defaults"

    def load(self) -> Mapping[str, Any]:
        return Config().to_dict()

    def describe(self) -> str:
        return "Built-in defaults"


class TomlConfigSource(ConfigSource):
    """Load configuration data from a TOML document with include support."""

    def __init__(
        self,
        path: Path,
        *,
        name: str | None = None,
        include_key: str = DEFAULT_INCLUDE_KEY,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._root_path = path
        self.name = name or str(path)
        self._include_key = include_key
        self._env = env or os.environ

    def load(self) -> Mapping[str, Any]:
        return self._load(self._root_path, ())

    def _load(self, path: Path, stack: tuple[Path, ...]) -> Mapping[str, Any]:
        if not path.exists():
            return {}
        if path in stack:
            include_chain = " -> ".join(str(entry) for entry in (*stack, path))
            raise ConfigError(f"Circular include detected: {include_chain}")
        resolved = path.resolve()
        stat = resolved.stat()
        cache_key = (resolved, stat.st_mtime_ns)
        if cached := _TOML_CACHE.get(cache_key):
            data = copy.deepcopy(cached)
        else:
            with resolved.open("rb") as handle:
                data = tomllib.load(handle)
            _TOML_CACHE[cache_key] = copy.deepcopy(data)
        if not isinstance(data, MutableMapping):
            raise ConfigError(f"Configuration at {path} must be a table")
        document: dict[str, Any] = dict(data)
        includes = document.pop(self._include_key, None)
        merged: dict[str, Any] = {}
        for include_path in self._coerce_includes(includes, path.parent):
            fragment = self._load(include_path, stack + (path,))
            merged = _deep_merge(merged, fragment)
        merged = _deep_merge(merged, document)
        return _expand_env(merged, self._env)

    def _coerce_includes(self, raw: Any, base_dir: Path) -> Iterable[Path]:
        if raw is None:
            return []
        if isinstance(raw, (str, Path)):
            return [self._resolve_path(Path(raw), base_dir)]
        if isinstance(raw, MutableMapping):
            return [self._resolve_path(Path(value), base_dir) for value in raw.values()]
        if isinstance(raw, Iterable):
            return [self._resolve_path(Path(item), base_dir) for item in raw]
        raise ConfigError(f"Unsupported include declaration: {raw!r}")

    @staticmethod
    def _resolve_path(path: Path, base_dir: Path) -> Path:
        return path if path.is_absolute() else (base_dir / path)

    def describe(self) -> str:
        return f"TOML configuration at {self.name}"


class PyProjectConfigSource(TomlConfigSource):
    """Read configuration from ``[tool.pyqa]`` within ``pyproject.toml``."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, name=str(path))

    def load(self) -> Mapping[str, Any]:
        data = super().load()
        tool_section = data.get(PYPROJECT_TOOL_KEY)
        if not isinstance(tool_section, Mapping):
            return {}
        pyqa_section = tool_section.get(PYPROJECT_SECTION_KEY)
        if not isinstance(pyqa_section, Mapping):
            return {}
        return _normalise_pyproject_payload(dict(pyqa_section))

    def describe(self) -> str:
        return f"pyproject.toml ({self.name})"


__all__ = [
    "CONFIG_KEY",
    "DEFAULT_INCLUDE_KEY",
    "DefaultConfigSource",
    "PyProjectConfigSource",
    "TomlConfigSource",
]
