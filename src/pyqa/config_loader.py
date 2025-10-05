# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Config loading utilities with layered precedence and traceability."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from operator import attrgetter
from pathlib import Path
from typing import Any, Final, Generic, cast

from pydantic import BaseModel, ConfigDict, Field

from .config import Config, ConfigError
from .config.loaders import CONFIG_KEY, DefaultConfigSource, PyProjectConfigSource, TomlConfigSource
from .config.sections import (
    FieldName,
    ModelT,
    PathResolver,
    SectionName,
    _model_replace,
    _SectionMerger,
    build_section_mergers,
)
from .config.utils import (
    _deep_merge,
    _normalise_fragment,
    generate_config_schema,
)
from .interfaces.config import ConfigSource
from .tools.settings import TOOL_SETTING_SCHEMA


@dataclass(slots=True, frozen=True)
class _SectionProcessor(Generic[ModelT]):
    """Apply a section-specific merger to a :class:`Config` instance."""

    name: SectionName
    merger: _SectionMerger[ModelT]
    getter: Callable[[Config], ModelT]
    setter: Callable[[Config, ModelT], Config]

    def merge_into(
        self,
        config: Config,
        data: Mapping[str, Any],
        *,
        source: str,
    ) -> tuple[Config, list[FieldUpdate]]:
        """Merge raw section data into ``config`` and return updates.

        Args:
            config: Configuration instance to update.
            data: Raw mapping containing section overrides.
            source: Source identifier for provenance reporting.

        Returns:
            tuple[Config, list[FieldUpdate]]: Updated config plus
            ``FieldUpdate`` entries describing mutations.
        """

        section_raw = data.get(self.name)
        current_model = self.getter(config)
        merged_model, changes = self.merger.merge(current_model, section_raw)
        if not changes:
            return config, []
        updated_config = self.setter(config, merged_model)
        updates = [
            FieldUpdate(section=self.name, field=field, source=source, value=value) for field, value in changes.items()
        ]
        return updated_config, updates


class FieldUpdate(BaseModel):
    """Description of a single configuration field mutation."""

    model_config = ConfigDict(validate_assignment=True)

    section: SectionName
    field: FieldName
    source: str
    value: Any


class ConfigLoadResult(BaseModel):
    """Container bundling a resolved config with provenance metadata."""

    model_config = ConfigDict(validate_assignment=True)

    config: Config
    updates: list[FieldUpdate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    snapshots: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ConfigLoader:
    """Apply layered configuration sources with predictable precedence."""

    def __init__(
        self,
        *,
        project_root: Path,
        sources: Sequence[ConfigSource],
        resolver: PathResolver | None = None,
    ) -> None:
        """Initialise a loader that merges the supplied configuration sources.

        Args:
            project_root: Directory that anchors relative paths.
            sources: Ordered collection of configuration sources.
            resolver: Optional resolver override enabling tests to inject
                alternate root semantics.
        """

        if not sources:
            raise ValueError("at least one configuration source is required")
        self._sources = list(sources)
        self._project_root = project_root.resolve()
        self._resolver = resolver or PathResolver(project_root=self._project_root)
        self._merger = _ConfigMerger(self._resolver)

    @classmethod
    def for_root(
        cls,
        project_root: Path,
        *,
        user_config: Path | None = None,
        project_config: Path | None = None,
    ) -> ConfigLoader:
        """Build a loader that respects user, project, and default sources.

        Args:
            project_root: Workspace root used to discover configuration files.
            user_config: Optional path to a user-level override.
            project_config: Optional project-level override path.

        Returns:
            ConfigLoader: Loader configured with default precedence ordering.
        """

        root = project_root.resolve()
        home_config = user_config if user_config is not None else Path.home() / ".py_qa.toml"
        project_file = project_config if project_config is not None else root / ".py_qa.toml"
        pyproject = root / "pyproject.toml"
        sources: list[ConfigSource] = [
            DefaultConfigSource(),
            TomlConfigSource(home_config, name=str(home_config)),
        ]
        if pyproject.exists():
            sources.append(PyProjectConfigSource(pyproject))
        sources.append(TomlConfigSource(project_file, name=str(project_file)))
        return cls(project_root=root, sources=sources)

    def load(self, *, strict: bool = False) -> Config:
        """Return the resolved configuration without provenance metadata.

        Args:
            strict: When ``True`` any collected warnings raise a
                :class:`ConfigError`.

        Returns:
            Config: Fully merged configuration model.
        """

        return self.load_with_trace(strict=strict).config

    def load_with_trace(self, *, strict: bool = False) -> ConfigLoadResult:
        """Return the resolved configuration with trace metadata.

        Args:
            strict: When ``True`` raise if warnings were emitted during merge.

        Returns:
            ConfigLoadResult: Resolved configuration and provenance details.
        """

        config = Config().model_copy(deep=True)
        updates: list[FieldUpdate] = []
        warnings: list[str] = []
        snapshots: dict[str, dict[str, Any]] = {}
        for source in self._sources:
            if not (fragment := source.load()):
                continue
            if not (normalised := _normalise_fragment(fragment)):
                continue
            config, changed, new_warnings = self._merger.apply(config, normalised, source.name)
            updates.extend(changed)
            warnings.extend(new_warnings)
            snapshots[source.name] = _config_to_snapshot(config)
        if auto_updates := _auto_discover_tool_settings(config, self._project_root):
            updates.extend(auto_updates)
            snapshots["auto"] = _config_to_snapshot(config)
        snapshots["final"] = _config_to_snapshot(config)
        if strict and warnings:
            raise ConfigError("; ".join(warnings))
        return ConfigLoadResult(
            config=config,
            updates=updates,
            warnings=warnings,
            snapshots=snapshots,
        )


def load_config(project_root: Path) -> Config:
    """Load configuration for ``project_root`` using the default tiered sources."""
    return ConfigLoader.for_root(project_root).load()


class _ConfigMerger:
    """Apply mapping data onto strongly typed configuration objects."""

    def __init__(self, resolver: PathResolver) -> None:
        section_specs = build_section_mergers(resolver)
        self._sections = tuple(self._build_section(merger, attr_name) for attr_name, merger in section_specs)

    def apply(
        self,
        config: Config,
        data: Mapping[str, Any],
        source: str,
    ) -> tuple[Config, list[FieldUpdate], list[str]]:
        """Apply ``data`` to ``config`` returning the updated model.

        Args:
            config: Existing configuration instance.
            data: Raw mapping of overrides.
            source: Identifier describing the origin of the overrides.

        Returns:
            tuple[Config, list[FieldUpdate], list[str]]: Updated configuration,
            accumulated field updates, and warnings emitted during merge.
        """

        updates: list[FieldUpdate] = []
        warnings: list[str] = []
        merged_config = config
        for processor in self._sections:
            merged_config, section_updates = processor.merge_into(
                merged_config,
                data,
                source=source,
            )
            updates.extend(section_updates)

        tool_settings, tool_updates, tool_warnings = _merge_tool_settings(
            merged_config.tool_settings,
            data.get("tools"),
            source,
        )
        warnings.extend(tool_warnings)
        if tool_updates:
            merged_config = _model_replace(merged_config, tool_settings=tool_settings)
            for tool, value in tool_updates.items():
                updates.append(
                    FieldUpdate(
                        section="tool_settings",
                        field=tool,
                        source=source,
                        value=value,
                    )
                )

        severity_rules = _merge_severity_rules(
            merged_config.severity_rules,
            data.get("severity_rules"),
        )
        if severity_rules != merged_config.severity_rules:
            merged_config = _model_replace(merged_config, severity_rules=severity_rules)
            updates.append(
                FieldUpdate(
                    section="root",
                    field="severity_rules",
                    source=source,
                    value=list(severity_rules),
                ),
            )

        return merged_config, updates, warnings

    def sections(self) -> tuple[SectionName, ...]:
        """Return section identifiers managed by this merger instance.

        Returns:
            tuple[SectionName, ...]: Ordered section identifiers processed
            during configuration merges.

        """

        return tuple(processor.name for processor in self._sections)

    @staticmethod
    def _build_section(
        merger: _SectionMerger[ModelT],
        attr_name: str,
    ) -> _SectionProcessor[ModelT]:
        """Return a section processor binding ``merger`` to a config attribute."""

        getter = cast(Callable[[Config], ModelT], attrgetter(attr_name))

        def setter(config: Config, value: ModelT, *, name: str = attr_name) -> Config:
            return _model_replace(config, **{name: value})

        return _SectionProcessor[ModelT](
            name=merger.section,
            merger=merger,
            getter=getter,
            setter=setter,
        )


def _merge_severity_rules(current: list[str], raw: Any) -> list[str]:
    """Return the merged severity rules list while validating inputs.

    Args:
        current: Existing severity rule list.
        raw: Raw iterable of severity rule strings or ``None``.

    Returns:
        list[str]: Updated severity rule list preserving order.
    """

    if raw is None:
        return list(current)
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        raise ConfigError("severity_rules must be an array of strings")
    rules: list[str] = []
    for value in raw:
        if not isinstance(value, str):
            raise ConfigError("severity_rules entries must be strings")
        rules.append(value)
    return rules


def _merge_tool_settings(
    current: Mapping[str, Mapping[str, Any]],
    raw: Any,
    source: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    """Merge tool-specific configuration dictionaries.

    Args:
        current: Existing tool configuration mapping.
        raw: Raw mapping containing overrides.
        source: Source identifier used for warning messages.

    Returns:
        tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
            Updated tool settings, per-tool diffs, and warnings.
    """

    result: dict[str, dict[str, Any]] = {tool: dict(settings) for tool, settings in current.items()}
    if raw is None:
        return result, {}, []
    if not isinstance(raw, Mapping):
        raise ConfigError("tools section must be a table")
    updates: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for tool, value in raw.items():
        merged, tool_update, tool_warnings = _merge_tool_entry(
            tool,
            value,
            result.get(tool, {}),
            source,
        )
        result[tool] = merged
        if tool_update is not None:
            updates[tool] = tool_update
        warnings.extend(tool_warnings)
    return result, updates, warnings


_RESERVED_TOOL_KEYS: Final[frozenset[str]] = frozenset({"duplicates", "complexity", "strictness", "severity"})


def _merge_tool_entry(
    tool: str,
    raw_value: Any,
    existing: Mapping[str, Any],
    source: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[str]]:
    """Merge a single tool configuration mapping while collecting warnings."""

    if tool in _RESERVED_TOOL_KEYS:
        return dict(existing), None, []
    if not isinstance(raw_value, Mapping):
        raise ConfigError(f"tools.{tool} section must be a table")

    schema = TOOL_SETTING_SCHEMA.get(tool)
    warnings: list[str] = []
    if schema is None:
        warnings.append(f"[{source}] Unknown tool '{tool}' in tool settings")

    merged = _deep_merge(existing, raw_value)
    update = merged if merged != existing else None

    if schema:
        unknown_keys = [key for key in raw_value.keys() if key not in schema]
        for key in unknown_keys:
            warnings.append(
                f"[{source}] Unknown option '{key}' for tool '{tool}' in tool settings",
            )

    return merged, update, warnings


def _config_to_snapshot(config: Config) -> dict[str, Any]:
    """Produce a serialisable snapshot of the configuration model.

    Args:
        config: Configuration model to serialise.

    Returns:
        dict[str, Any]: Serialisable payload capturing the configuration.
    """

    snapshot = config.to_dict()
    tools = snapshot.pop("tools", {})
    snapshot["tool_settings"] = tools
    return snapshot


def _auto_discover_tool_settings(config: Config, root: Path) -> list[FieldUpdate]:
    """Populate tool settings with auto-discovered config file references.

    Args:
        config: Configuration model to mutate in place.
        root: Project root to inspect for tool-specific configuration files.

    Returns:
        list[FieldUpdate]: Field updates recording discovered tool settings.
    """

    updates: list[FieldUpdate] = []
    for tool, filenames in AUTO_TOOL_CONFIG_FILES.items():
        existing = config.tool_settings.get(tool)
        current_settings = dict(existing) if existing else {}
        if CONFIG_KEY in current_settings:
            continue
        selected: str | None = None
        for name in filenames:
            candidate = root / name
            if candidate.exists():
                try:
                    selected = str(candidate.relative_to(root))
                except ValueError:
                    selected = str(candidate)
                break
        if selected is None:
            continue
        current_settings[CONFIG_KEY] = selected
        config.tool_settings[tool] = current_settings
        updates.append(
            FieldUpdate(
                section="tool_settings",
                field=tool,
                source="auto",
                value=dict(current_settings),
            ),
        )
    return updates


AUTO_TOOL_CONFIG_FILES: dict[str, list[str]] = {
    "ruff": ["ruff.toml"],
    "ruff-format": ["ruff.toml"],
    "black": ["black.toml"],
    "isort": [".isort.cfg", "isort.cfg"],
    "pyright": ["pyrightconfig.json", "pyprojectconfig.json"],
    "bandit": ["bandit.yaml", "bandit.yml"],
    "eslint": [
        ".eslintrc",
        ".eslintrc.json",
        ".eslintrc.js",
        ".eslintrc.cjs",
        "eslint.config.js",
        "eslint.config.cjs",
        "eslint.config.mjs",
    ],
    "prettier": [
        ".prettierrc",
        ".prettierrc.json",
        ".prettierrc.js",
        ".prettierrc.cjs",
        "prettier.config.js",
        "prettier.config.cjs",
    ],
    "tsc": ["tsconfig.json", "tsconfig.base.json"],
    "golangci-lint": [
        ".golangci.yml",
        ".golangci.yaml",
        "golangci.yml",
        "golangci.yaml",
    ],
}


_TOML_CACHE: dict[tuple[Path, int], Mapping[str, Any]] = {}


__all__ = [
    "ConfigLoadResult",
    "ConfigLoader",
    "ConfigError",
    "FieldUpdate",
    "generate_config_schema",
    "load_config",
]
