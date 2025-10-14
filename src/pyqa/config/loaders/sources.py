# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Concrete configuration sources (defaults, TOML, pyproject)."""

from __future__ import annotations

import copy
import os
import tomllib
from collections.abc import Iterable, Mapping, MutableMapping
from pathlib import Path
from typing import Final

from ...interfaces.config import ConfigSource
from ..defaults import default_config_payload
from ..models import ConfigError
from ..types import ConfigFragment, ConfigValue
from ..utils import _deep_merge, _expand_env, _normalise_pyproject_payload

DEFAULT_INCLUDE_KEY: Final[str] = "include"
PYPROJECT_TOOL_KEY: Final[str] = "tool"
PYPROJECT_SECTION_KEY: Final[str] = "pyqa"
CONFIG_KEY: Final[str] = "config"

_TOML_CACHE: dict[tuple[Path, int], ConfigFragment] = {}


class DefaultConfigSource(ConfigSource):
    """Return the built-in defaults as a configuration fragment."""

    def __init__(self) -> None:
        self.name = "defaults"

    def load(self) -> ConfigFragment:
        """Return the built-in configuration payload.

        Returns:
            Mapping containing default configuration values shipped with pyqa.
        """

        return default_config_payload()

    def describe(self) -> str:
        """Return a human-readable description of this source.

        Returns:
            Description string identifying the defaults source.
        """

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

    def load(self) -> ConfigFragment:
        """Return configuration data resolved from the root TOML document.

        Returns:
            Mapping representing the merged configuration result.
        """

        return self._load(self._root_path, ())

    def _load(self, path: Path, stack: tuple[Path, ...]) -> dict[str, ConfigValue]:
        """Return merged configuration for ``path`` while tracking recursion.

        Args:
            path: File system path to the TOML document being processed.
            stack: Tuple of paths already traversed to detect cycles.

        Returns:
            Mapping of configuration values for the resolved document.
        """

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
        document: dict[str, ConfigValue] = dict(data)
        includes = document.pop(self._include_key, None)
        merged: dict[str, ConfigValue] = {}
        for include_path in self._coerce_includes(includes, path.parent):
            fragment = self._load(include_path, stack + (path,))
            merged = _deep_merge(merged, fragment)
        merged = _deep_merge(merged, document)
        return _expand_env(merged, self._env)

    def _coerce_includes(self, raw: ConfigValue, base_dir: Path) -> Iterable[Path]:
        """Return include paths derived from ``raw`` relative to ``base_dir``.

        Args:
            raw: Include declaration in the TOML document.
            base_dir: Directory used to resolve relative include paths.

        Returns:
            Iterable of resolved include paths.
        """

        if raw is None:
            return []
        if isinstance(raw, Mapping):
            return [self._coerce_include_value(value, base_dir) for value in raw.values()]
        if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
            return [self._coerce_include_value(item, base_dir) for item in raw]
        return [self._coerce_include_value(raw, base_dir)]

    def _coerce_include_value(self, value: ConfigValue, base_dir: Path) -> Path:
        """Return a resolved include path for ``value`` relative to ``base_dir``."""

        if isinstance(value, Path):
            return self._resolve_path(value, base_dir)
        if isinstance(value, str):
            return self._resolve_path(Path(value), base_dir)
        raise ConfigError(f"Unsupported include declaration: {value!r}")

    @staticmethod
    def _resolve_path(path: Path, base_dir: Path) -> Path:
        """Return an absolute path for ``path`` relative to ``base_dir``.

        Args:
            path: Include path originating from a TOML document.
            base_dir: Directory anchoring relative include paths.

        Returns:
            Absolute path pointing to the include target.
        """

        return path if path.is_absolute() else (base_dir / path)

    def describe(self) -> str:
        """Return a description string for the TOML source.

        Returns:
            Description string referencing the underlying file path.
        """

        return f"TOML configuration at {self.name}"


class PyProjectConfigSource(TomlConfigSource):
    """Read configuration from ``[tool.pyqa]`` within ``pyproject.toml``."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, name=str(path))

    def load(self) -> ConfigFragment:
        """Return configuration extracted from ``[tool.pyqa]`` sections.

        Returns:
            Mapping representing the normalised pyqa configuration payload.
        """

        data = super().load()
        tool_section = data.get(PYPROJECT_TOOL_KEY)
        if not isinstance(tool_section, Mapping):
            return {}
        pyqa_section = tool_section.get(PYPROJECT_SECTION_KEY)
        if not isinstance(pyqa_section, Mapping):
            return {}
        return _normalise_pyproject_payload(dict(pyqa_section))

    def describe(self) -> str:
        """Return a human-readable description of the pyproject source.

        Returns:
            Description string referencing the pyproject file path.
        """

        return f"pyproject.toml ({self.name})"


__all__ = [
    "CONFIG_KEY",
    "DEFAULT_INCLUDE_KEY",
    "DefaultConfigSource",
    "PyProjectConfigSource",
    "TomlConfigSource",
]
