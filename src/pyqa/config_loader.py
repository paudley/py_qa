# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Config loading utilities with layered precedence and traceability."""

from __future__ import annotations

import copy
import os
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from operator import attrgetter
from pathlib import Path
from typing import (
    Any,
    Final,
    Generic,
    Protocol,
    TypeVar,
    cast,
)

try:  # Python 3.11+ includes tomllib in the stdlib. Fallbacks unsupported.
    import tomllib
except ModuleNotFoundError as exc:
    raise RuntimeError("tomllib is required to parse configuration files") from exc

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import (
    CleanConfig,
    Config,
    ConfigError,
    DedupeConfig,
    ExecutionConfig,
    FileDiscoveryConfig,
    LicenseConfig,
    OutputConfig,
    QualityConfigSection,
    UpdateConfig,
)
from .config_utils import (
    _coerce_iterable,
    _coerce_optional_int,
    _coerce_string_sequence,
    _deep_merge,
    _existing_unique_paths,
    _expand_env,
    _normalise_fragment,
    _normalise_pyproject_payload,
    _normalize_min_severity,
    _normalize_output_mode,
    _normalize_tool_filters,
    _unique_paths,
    generate_config_schema,
)
from .tools.settings import TOOL_SETTING_SCHEMA

SectionName = str
FieldName = str

INCLUDE_KEY_DEFAULT: Final[str] = "include"
PYPROJECT_TOOL_KEY: Final[str] = "tool"
PYPROJECT_SECTION_KEY: Final[str] = "pyqa"
CONFIG_KEY: Final[str] = "config"
FILE_DISCOVERY_ROOTS_KEY: Final[str] = "roots"
FILE_DISCOVERY_EXCLUDES_KEY: Final[str] = "excludes"
FILE_DISCOVERY_EXPLICIT_KEY: Final[str] = "explicit_files"
FILE_DISCOVERY_LIMIT_KEY: Final[str] = "limit_to"
OUTPUT_TOOL_FILTERS_KEY: Final[str] = "tool_filters"
OUTPUT_MIN_SEVERITY_KEY: Final[str] = "pr_summary_min_severity"
OUTPUT_REPORT_OUT_KEY: Final[str] = "report_out"
OUTPUT_SARIF_OUT_KEY: Final[str] = "sarif_out"
OUTPUT_PR_SUMMARY_OUT_KEY: Final[str] = "pr_summary_out"
EXECUTION_ONLY_KEY: Final[str] = "only"
EXECUTION_LANGUAGES_KEY: Final[str] = "languages"
EXECUTION_ENABLE_KEY: Final[str] = "enable"
LICENSE_ALLOW_ALTERNATE_KEY: Final[str] = "allow_alternate_spdx"
LICENSE_EXCEPTIONS_KEY: Final[str] = "exceptions"
QUALITY_CHECKS_KEY: Final[str] = "checks"
QUALITY_SKIP_GLOBS_KEY: Final[str] = "skip_globs"
QUALITY_SCHEMA_TARGETS_KEY: Final[str] = "schema_targets"
QUALITY_PROTECTED_BRANCHES_KEY: Final[str] = "protected_branches"
CLEAN_PATTERNS_KEY: Final[str] = "patterns"
CLEAN_TREES_KEY: Final[str] = "trees"
UPDATE_SKIP_PATTERNS_KEY: Final[str] = "skip_patterns"
UPDATE_ENABLED_MANAGERS_KEY: Final[str] = "enabled_managers"
DEDUPE_PREFER_KEY: Final[str] = "dedupe_prefer"

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(slots=True, frozen=True)
class _SectionProcessor(Generic[ModelT]):
    """Apply a section-specific merger to a :class:`Config` instance."""

    name: SectionName
    merger: _SectionMerger
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
            tuple[Config, list[FieldUpdate]]: Updated config plus FieldUpdate
            entries describing mutations.
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


class ConfigSource(Protocol):
    """Provide configuration fragments and metadata about their origin."""

    name: str

    def load(self) -> Mapping[str, Any]:
        """Return a mapping of configuration overrides.

        Returns:
            Mapping[str, Any]: Concrete configuration fragment contributed by
            the source.
        """

        raise NotImplementedError

    def describe(self) -> str:
        """Return a human-readable description of the source."""

        raise NotImplementedError


class DefaultConfigSource:
    """Return the built-in defaults as a configuration fragment."""

    name = "defaults"

    def load(self) -> Mapping[str, Any]:
        """Return an in-memory snapshot of baseline configuration values.

        Returns:
            Mapping[str, Any]: Serialised configuration produced from the
            default :class:`Config` model.
        """

        return Config().to_dict()

    def describe(self) -> str:
        """Return a short identifier for UI/diagnostic use.

        Returns:
            str: Human-readable identifier for the source.
        """

        return "Built-in defaults"


class TomlConfigSource:
    """Load configuration data from a TOML document with include support."""

    def __init__(
        self,
        path: Path,
        *,
        name: str | None = None,
        include_key: str = INCLUDE_KEY_DEFAULT,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._root_path = path
        self.name = name or str(path)
        self._include_key = include_key
        self._env = env or os.environ

    def load(self) -> Mapping[str, Any]:
        """Load, expand, and merge the TOML document for this source.

        Returns:
            Mapping[str, Any]: Normalised configuration data aggregated across
            include directives.
        """

        return self._load(self._root_path, ())

    def _load(self, path: Path, stack: tuple[Path, ...]) -> Mapping[str, Any]:
        """Return the merged document at ``path`` while guarding recursion.

        Args:
            path: TOML file to parse.
            stack: Tuple recording the include traversal for cycle detection.

        Returns:
            Mapping[str, Any]: Parsed data with includes resolved.
        """

        if not path.exists():
            return {}
        if path in stack:
            raise ConfigError(
                "Circular include detected: " + " -> ".join(str(entry) for entry in stack + (path,)),
            )
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
        """Return absolute include paths derived from ``raw`` declarations.

        Args:
            raw: Raw include entries found in the TOML document.
            base_dir: Directory used to resolve relative include references.

        Returns:
            Iterable[Path]: Absolute include paths to parse recursively.
        """

        if raw is None:
            return []
        if isinstance(raw, (str, Path)):
            raw = [raw]
        if not isinstance(raw, Iterable) or isinstance(raw, (bytes, str)):
            raise ConfigError(f"Include declarations in {self._root_path} must be a string or list")
        paths: list[Path] = []
        for entry in raw:
            if not isinstance(entry, (str, Path)):
                raise ConfigError("Include entries must be strings or paths")
            candidate = Path(entry).expanduser()
            if not candidate.is_absolute():
                candidate = (base_dir / candidate).resolve()
            paths.append(candidate)
        return paths

    def describe(self) -> str:
        """Return a short diagnostic string for this TOML source.

        Returns:
            str: Human-readable identifier for the source.
        """

        return f"TOML configuration at {self.name}"


class PyProjectConfigSource(TomlConfigSource):
    """Read configuration from ``[tool.pyqa]`` within ``pyproject.toml``."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, name=str(path))

    def load(self) -> Mapping[str, Any]:
        """Return the ``tool.pyqa`` fragment from ``pyproject.toml`` if present."""

        data = super().load()
        tool_section = data.get(PYPROJECT_TOOL_KEY)
        if not isinstance(tool_section, Mapping):
            return {}
        pyqa_section = tool_section.get(PYPROJECT_SECTION_KEY)
        if not isinstance(pyqa_section, Mapping):
            return {}
        return _normalise_pyproject_payload(dict(pyqa_section))

    def describe(self) -> str:
        """Return a short diagnostic string for this ``pyproject`` source.

        Returns:
            str: Human-readable identifier for the source.
        """

        return f"pyproject.toml ({self.name})"


class PathResolver(BaseModel):
    """Convert path-like values relative to the project root."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_root: Path

    @model_validator(mode="after")
    def _normalise_root(self) -> PathResolver:
        object.__setattr__(self, "project_root", self.project_root.resolve())
        return self

    def resolve(self, value: Path | str) -> Path:
        """Return an absolute path for ``value`` relative to the project root.

        Args:
            value: Path-like input from user configuration.

        Returns:
            Path: Resolved absolute filesystem path.
        """

        candidate = value if isinstance(value, Path) else Path(value)
        candidate = candidate.expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.project_root / candidate).resolve()

    def resolve_optional(self, value: Path | str | None) -> Path | None:
        """Resolve ``value`` while preserving ``None`` inputs.

        Args:
            value: Optional path-like value to resolve.

        Returns:
            Path | None: Resolved path or ``None`` when ``value`` is ``None``.
        """

        if value is None:
            return None
        return self.resolve(value)

    def resolve_iterable(self, values: Iterable[Path | str]) -> list[Path]:
        """Resolve a collection of path-like values.

        Args:
            values: Iterable of path-like entries to resolve.

        Returns:
            list[Path]: Resolved path entries.
        """

        return [self.resolve(value) for value in values]


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
        self._sections: tuple[_SectionProcessor[Any], ...] = (
            self._build_section(_FileDiscoverySection(resolver), "file_discovery"),
            self._build_section(_OutputSection(resolver), "output"),
            self._build_section(_ExecutionSection(resolver), "execution"),
            self._build_section(_DedupeSection(), "dedupe"),
            self._build_section(_LicenseSection(), "license"),
            self._build_section(_QualitySection(resolver), "quality"),
            self._build_section(_CleanSection(), "clean"),
            self._build_section(_UpdateSection(), "update"),
        )

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
            merged_config, section_updates = processor.merge_into(merged_config, data, source=source)
            updates.extend(section_updates)

        tool_settings, tool_updates, tool_warnings = _merge_tool_settings(
            merged_config.tool_settings,
            data.get("tools"),
            source,
        )
        warnings.extend(tool_warnings)
        if tool_updates:
            merged_config = _model_replace(merged_config, tool_settings=tool_settings)
            updates.extend(
                FieldUpdate(section="tool_settings", field=tool, source=source, value=value)
                for tool, value in tool_updates.items()
            )

        severity_rules = _merge_severity_rules(merged_config.severity_rules, data.get("severity_rules"))
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

    @staticmethod
    def _build_section(merger: _SectionMerger, attr_name: str) -> _SectionProcessor[Any]:
        """Return a section processor binding ``merger`` to a config attribute."""

        getter = cast(Callable[[Config], Any], attrgetter(attr_name))

        def setter(config: Config, value: Any, *, name: str = attr_name) -> Config:
            return _model_replace(config, **{name: value})

        return _SectionProcessor[Any](
            name=merger.section,
            merger=merger,
            getter=getter,
            setter=setter,
        )


class _SectionMerger:
    """Base utilities for section-specific merge implementations."""

    section: SectionName

    def describe_section(self) -> SectionName:
        """Return the section identifier managed by this merger."""

        return self.section

    @staticmethod
    def _ensure_mapping(raw: Any, section: str) -> Mapping[str, Any]:
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{section} section must be a table")
        return raw

    @staticmethod
    def _diff_model(current: BaseModel, updated: BaseModel) -> dict[str, Any]:
        current_data = current.model_dump(mode="python")
        updated_data = updated.model_dump(mode="python")
        result: dict[str, Any] = {}
        for key, value in updated_data.items():
            if current_data.get(key) != value:
                result[key] = value
        return result


class _FileDiscoverySection(_SectionMerger):
    section = "file_discovery"

    def __init__(self, resolver: PathResolver) -> None:
        self._resolver = resolver

    def merge(
        self,
        current: FileDiscoveryConfig,
        raw: Any,
    ) -> tuple[FileDiscoveryConfig, dict[str, Any]]:
        """Merge raw mapping data into the file discovery configuration.

        Args:
            current: Existing configuration values.
            raw: Raw mapping from the configuration fragment (may be ``None``).

        Returns:
            tuple[FileDiscoveryConfig, dict[str, Any]]: Updated configuration
            model paired with the changed field values.
        """

        data = self._ensure_mapping(raw, self.section)
        roots = list(current.roots)
        if FILE_DISCOVERY_ROOTS_KEY in data:
            raw_roots = _coerce_iterable(data[FILE_DISCOVERY_ROOTS_KEY], "file_discovery.roots")
            roots = _unique_paths(self._resolver.resolve_iterable(raw_roots))
        elif not roots:
            roots = [self._resolver.project_root]

        excludes = _unique_paths(current.excludes)
        if FILE_DISCOVERY_EXCLUDES_KEY in data:
            raw_excludes = _coerce_iterable(
                data[FILE_DISCOVERY_EXCLUDES_KEY],
                "file_discovery.excludes",
            )
            for resolved in self._resolver.resolve_iterable(raw_excludes):
                candidate = resolved.resolve()
                if candidate not in excludes:
                    excludes.append(candidate)

        explicit_files = _existing_unique_paths(current.explicit_files)
        if FILE_DISCOVERY_EXPLICIT_KEY in data:
            raw_explicit = _coerce_iterable(
                data[FILE_DISCOVERY_EXPLICIT_KEY],
                "file_discovery.explicit_files",
            )
            for resolved in self._resolver.resolve_iterable(raw_explicit):
                candidate = resolved.resolve()
                if candidate.exists() and candidate not in explicit_files:
                    explicit_files.append(candidate)

        limit_to = _unique_paths(current.limit_to)
        if FILE_DISCOVERY_LIMIT_KEY in data:
            raw_limits = _coerce_iterable(
                data[FILE_DISCOVERY_LIMIT_KEY],
                "file_discovery.limit_to",
            )
            limit_to = _unique_paths(self._resolver.resolve_iterable(raw_limits))

        updated = _model_replace(
            current,
            roots=roots,
            excludes=excludes,
            explicit_files=explicit_files,
            paths_from_stdin=data.get("paths_from_stdin", current.paths_from_stdin),
            changed_only=data.get("changed_only", current.changed_only),
            diff_ref=data.get("diff_ref", current.diff_ref),
            include_untracked=data.get("include_untracked", current.include_untracked),
            base_branch=data.get("base_branch", current.base_branch),
            limit_to=limit_to,
        )
        return updated, self._diff_model(current, updated)


class _OutputSection(_SectionMerger):
    section = "output"

    def __init__(self, resolver: PathResolver) -> None:
        self._resolver = resolver

    def merge(self, current: OutputConfig, raw: Any) -> tuple[OutputConfig, dict[str, Any]]:
        """Merge output section overrides into the model.

        Args:
            current: Existing output configuration.
            raw: Raw mapping sourced from configuration fragments.

        Returns:
            tuple[OutputConfig, dict[str, Any]]: Updated configuration paired
            with a diff of changed fields.
        """

        data = self._ensure_mapping(raw, self.section)
        tool_filters = {tool: patterns.copy() for tool, patterns in current.tool_filters.items()}
        if OUTPUT_TOOL_FILTERS_KEY in data:
            tool_filters = _normalize_tool_filters(
                data[OUTPUT_TOOL_FILTERS_KEY],
                current.tool_filters,
            )

        pr_summary_out = self._resolver.resolve_optional(
            data.get(OUTPUT_PR_SUMMARY_OUT_KEY, current.pr_summary_out),
        )
        report_out = self._resolver.resolve_optional(data.get(OUTPUT_REPORT_OUT_KEY, current.report_out))
        sarif_out = self._resolver.resolve_optional(data.get(OUTPUT_SARIF_OUT_KEY, current.sarif_out))

        output_mode = data.get("output", current.output)
        if not isinstance(output_mode, str):
            raise ConfigError("output.mode must be a string")
        normalized_output = _normalize_output_mode(output_mode)

        pr_summary_min = data.get(OUTPUT_MIN_SEVERITY_KEY, current.pr_summary_min_severity)
        if not isinstance(pr_summary_min, str):
            raise ConfigError("output.pr_summary_min_severity must be a string")
        normalized_min = _normalize_min_severity(pr_summary_min)

        updated = _model_replace(
            current,
            verbose=data.get("verbose", current.verbose),
            emoji=data.get("emoji", current.emoji),
            color=data.get("color", current.color),
            show_passing=data.get("show_passing", current.show_passing),
            output=normalized_output,
            pretty_format=data.get("pretty_format", current.pretty_format),
            group_by_code=data.get("group_by_code", current.group_by_code),
            report=data.get("report", current.report),
            report_out=report_out,
            report_include_raw=data.get("report_include_raw", current.report_include_raw),
            sarif_out=sarif_out,
            pr_summary_out=pr_summary_out,
            pr_summary_limit=data.get("pr_summary_limit", current.pr_summary_limit),
            pr_summary_min_severity=normalized_min,
            pr_summary_template=data.get("pr_summary_template", current.pr_summary_template),
            gha_annotations=data.get("gha_annotations", current.gha_annotations),
            annotations_use_json=data.get("annotations_use_json", current.annotations_use_json),
            quiet=data.get("quiet", current.quiet),
            tool_filters=tool_filters if tool_filters else current.tool_filters,
        )
        if updated.quiet:
            updated = _model_replace(updated, show_passing=False)
        return updated, self._diff_model(current, updated)


class _ExecutionSection(_SectionMerger):
    section = "execution"

    def __init__(self, resolver: PathResolver) -> None:
        self._resolver = resolver

    def merge(self, current: ExecutionConfig, raw: Any) -> tuple[ExecutionConfig, dict[str, Any]]:
        """Merge execution configuration overrides.

        Args:
            current: Existing execution configuration values.
            raw: Raw mapping containing overrides.

        Returns:
            tuple[ExecutionConfig, dict[str, Any]]: Updated configuration and
            per-field changes.
        """

        data = self._ensure_mapping(raw, self.section)
        cache_dir_value = data.get("cache_dir", current.cache_dir)
        cache_dir = self._resolver.resolve(cache_dir_value) if cache_dir_value is not None else current.cache_dir

        jobs = data.get("jobs", current.jobs)
        if bail := data.get("bail", current.bail):
            jobs = 1

        only = (
            list(_coerce_iterable(data[EXECUTION_ONLY_KEY], "execution.only"))
            if EXECUTION_ONLY_KEY in data
            else list(current.only)
        )
        languages = (
            list(_coerce_iterable(data[EXECUTION_LANGUAGES_KEY], "execution.languages"))
            if EXECUTION_LANGUAGES_KEY in data
            else list(current.languages)
        )
        enable = (
            list(_coerce_iterable(data[EXECUTION_ENABLE_KEY], "execution.enable"))
            if EXECUTION_ENABLE_KEY in data
            else list(current.enable)
        )

        updated = _model_replace(
            current,
            only=only,
            languages=languages,
            enable=enable,
            strict=data.get("strict", current.strict),
            jobs=jobs,
            fix_only=data.get("fix_only", current.fix_only),
            check_only=data.get("check_only", current.check_only),
            force_all=data.get("force_all", current.force_all),
            respect_config=data.get("respect_config", current.respect_config),
            cache_enabled=data.get("cache_enabled", current.cache_enabled),
            cache_dir=cache_dir,
            bail=bail,
            use_local_linters=data.get("use_local_linters", current.use_local_linters),
        )
        return updated, self._diff_model(current, updated)


class _LicenseSection(_SectionMerger):
    section = "license"

    def merge(self, current: LicenseConfig, raw: Any) -> tuple[LicenseConfig, dict[str, Any]]:
        """Merge license configuration overrides.

        Args:
            current: Existing license configuration.
            raw: Raw mapping containing overrides.

        Returns:
            tuple[LicenseConfig, dict[str, Any]]: Updated configuration and
            per-field changes.
        """

        data = self._ensure_mapping(raw, self.section)

        spdx = _coerce_optional_str_value(data.get("spdx"), current.spdx, "license.spdx")
        notice = _coerce_optional_str_value(data.get("notice"), current.notice, "license.notice")
        copyright_value = _coerce_optional_str_value(
            data.get("copyright"),
            current.copyright,
            "license.copyright",
        )
        year = _coerce_optional_str_value(data.get("year"), current.year, "license.year")

        require_spdx = _coerce_optional_bool(
            data.get("require_spdx"),
            current.require_spdx,
            "license.require_spdx",
        )
        require_notice = _coerce_optional_bool(
            data.get("require_notice"),
            current.require_notice,
            "license.require_notice",
        )

        allow_alternate = list(current.allow_alternate_spdx)
        if LICENSE_ALLOW_ALTERNATE_KEY in data:
            allow_alternate = _coerce_string_sequence(
                data[LICENSE_ALLOW_ALTERNATE_KEY],
                "license.allow_alternate_spdx",
            )

        exceptions = list(current.exceptions)
        if LICENSE_EXCEPTIONS_KEY in data:
            exceptions = _coerce_string_sequence(
                data[LICENSE_EXCEPTIONS_KEY],
                "license.exceptions",
            )

        updated = _model_replace(
            current,
            spdx=spdx,
            notice=notice,
            copyright=copyright_value,
            year=year,
            require_spdx=require_spdx,
            require_notice=require_notice,
            allow_alternate_spdx=allow_alternate,
            exceptions=exceptions,
        )
        return updated, self._diff_model(current, updated)


class _QualitySection(_SectionMerger):
    section = "quality"

    def __init__(self, resolver: PathResolver) -> None:
        self._resolver = resolver

    def merge(
        self,
        current: QualityConfigSection,
        raw: Any,
    ) -> tuple[QualityConfigSection, dict[str, Any]]:
        """Merge quality section overrides.

        Args:
            current: Existing quality configuration.
            raw: Raw mapping containing overrides.

        Returns:
            tuple[QualityConfigSection, dict[str, Any]]: Updated configuration
            and per-field changes.
        """

        data = self._ensure_mapping(raw, self.section)

        checks = list(current.checks)
        if QUALITY_CHECKS_KEY in data:
            checks = _coerce_string_sequence(data[QUALITY_CHECKS_KEY], "quality.checks")

        skip_globs = list(current.skip_globs)
        if QUALITY_SKIP_GLOBS_KEY in data:
            skip_globs = _coerce_string_sequence(data[QUALITY_SKIP_GLOBS_KEY], "quality.skip_globs")

        schema_targets = self._merge_schema_targets(
            data.get(QUALITY_SCHEMA_TARGETS_KEY),
            current.schema_targets,
        )

        warn_file_size = _coerce_optional_int(
            data.get("warn_file_size"),
            current.warn_file_size,
            "quality.warn_file_size",
        )
        max_file_size = _coerce_optional_int(
            data.get("max_file_size"),
            current.max_file_size,
            "quality.max_file_size",
        )

        protected_branches = list(current.protected_branches)
        if QUALITY_PROTECTED_BRANCHES_KEY in data:
            protected_branches = _coerce_string_sequence(
                data[QUALITY_PROTECTED_BRANCHES_KEY],
                "quality.protected_branches",
            )

        updated = _model_replace(
            current,
            checks=checks,
            skip_globs=skip_globs,
            schema_targets=schema_targets,
            warn_file_size=warn_file_size,
            max_file_size=max_file_size,
            protected_branches=protected_branches,
        )
        return updated, self._diff_model(current, updated)

    def _merge_schema_targets(
        self,
        raw: Any,
        current: Sequence[Path],
    ) -> list[Path]:
        """Return unique, resolved schema target paths.

        Args:
            raw: Raw collection drawn from configuration data.
            current: Existing schema target paths.

        Returns:
            list[Path]: Updated schema targets.
        """

        if raw is None:
            return list(current)
        raw_targets = _coerce_iterable(raw, "quality.schema_targets")
        resolved: list[Path] = []
        seen: set[Path] = set()
        for entry in raw_targets:
            if not isinstance(entry, (str, Path)):
                raise ConfigError("quality.schema_targets entries must be paths")
            candidate = self._resolver.resolve(entry)
            if candidate not in seen:
                seen.add(candidate)
                resolved.append(candidate)
        return resolved


class _CleanSection(_SectionMerger):
    section = "clean"

    def merge(self, current: CleanConfig, raw: Any) -> tuple[CleanConfig, dict[str, Any]]:
        """Merge clean section overrides.

        Args:
            current: Existing clean configuration.
            raw: Raw mapping containing overrides.

        Returns:
            tuple[CleanConfig, dict[str, Any]]: Updated configuration and
            per-field changes.
        """

        data = self._ensure_mapping(raw, self.section)
        patterns = list(current.patterns)
        if CLEAN_PATTERNS_KEY in data:
            patterns = _coerce_string_sequence(data[CLEAN_PATTERNS_KEY], "clean.patterns")

        trees = list(current.trees)
        if CLEAN_TREES_KEY in data:
            trees = _coerce_string_sequence(data[CLEAN_TREES_KEY], "clean.trees")

        updated = _model_replace(current, patterns=patterns, trees=trees)
        return updated, self._diff_model(current, updated)


class _UpdateSection(_SectionMerger):
    section = "update"

    def merge(self, current: UpdateConfig, raw: Any) -> tuple[UpdateConfig, dict[str, Any]]:
        """Merge update section overrides.

        Args:
            current: Existing update configuration.
            raw: Raw mapping containing overrides.

        Returns:
            tuple[UpdateConfig, dict[str, Any]]: Updated configuration and
            per-field changes.
        """

        data = self._ensure_mapping(raw, self.section)

        skip_patterns = list(current.skip_patterns)
        if UPDATE_SKIP_PATTERNS_KEY in data:
            skip_patterns = _coerce_string_sequence(
                data[UPDATE_SKIP_PATTERNS_KEY],
                "update.skip_patterns",
            )

        enabled_managers = list(current.enabled_managers)
        if UPDATE_ENABLED_MANAGERS_KEY in data:
            enabled_managers = _coerce_string_sequence(
                data[UPDATE_ENABLED_MANAGERS_KEY],
                "update.enabled_managers",
            )

        updated = _model_replace(
            current,
            skip_patterns=skip_patterns,
            enabled_managers=enabled_managers,
        )
        return updated, self._diff_model(current, updated)


class _DedupeSection(_SectionMerger):
    section = "dedupe"

    def merge(self, current: DedupeConfig, raw: Any) -> tuple[DedupeConfig, dict[str, Any]]:
        """Merge dedupe configuration overrides.

        Args:
            current: Existing dedupe configuration.
            raw: Raw mapping containing overrides.

        Returns:
            tuple[DedupeConfig, dict[str, Any]]: Updated configuration and
            per-field changes.
        """

        data = self._ensure_mapping(raw, self.section)
        updated = _model_replace(
            current,
            dedupe=data.get("dedupe", current.dedupe),
            dedupe_by=data.get("dedupe_by", current.dedupe_by),
            dedupe_prefer=list(data.get(DEDUPE_PREFER_KEY, current.dedupe_prefer)),
            dedupe_line_fuzz=data.get("dedupe_line_fuzz", current.dedupe_line_fuzz),
            dedupe_same_file_only=data.get("dedupe_same_file_only", current.dedupe_same_file_only),
        )
        return updated, self._diff_model(current, updated)


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
        if not isinstance(value, Mapping):
            raise ConfigError(f"tools.{tool} section must be a table")
        if tool in {"duplicates", "complexity", "strictness", "severity"}:
            continue
        if (schema := TOOL_SETTING_SCHEMA.get(tool)) is None:
            warnings.append(f"[{source}] Unknown tool '{tool}' in tool settings")
        existing = result.get(tool, {})
        if (merged := _deep_merge(existing, value)) != existing:
            result[tool] = merged
            updates[tool] = merged
        if schema:
            for key in value.keys():
                if key not in schema:
                    warnings.append(
                        f"[{source}] Unknown option '{key}' for tool '{tool}' in tool settings",
                    )
    return result, updates, warnings


def _coerce_optional_str_value(value: Any, current: str | None, context: str) -> str | None:
    """Return cleaned string values allowing ``None`` defaults.

    Args:
        value: Raw value to coerce.
        current: Existing string value (may be ``None``).
        context: Field context for error messaging.

    Returns:
        str | None: Sanitised string or ``None`` when blank or unspecified.
    """

    if value is None:
        return current
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    raise ConfigError(f"{context} must be a string")


def _coerce_optional_bool(value: Any, current: bool, context: str) -> bool:
    """Return cleaned bool values allowing ``None`` defaults.

    Args:
        value: Raw value to coerce.
        current: Existing boolean value.
        context: Field context for error messaging.

    Returns:
        bool: Sanitised boolean value.
    """

    if value is None:
        return current
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{context} must be a boolean")


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


def _model_replace(instance: ModelT, **updates: Any) -> ModelT:
    """Return a defensive deep copy of ``instance`` with ``updates`` applied.

    Args:
        instance: Pydantic model instance to clone.
        **updates: Field overrides applied to the clone.

    Returns:
        ModelT: Deep-copied model with overrides applied.
    """

    if not isinstance(instance, BaseModel):  # defensive guard for legacy usage
        raise TypeError("_model_replace expects a Pydantic BaseModel instance")
    return cast("ModelT", instance.model_copy(update=updates, deep=True))


_TOML_CACHE: dict[tuple[Path, int], Mapping[str, Any]] = {}


__all__ = [
    "ConfigLoadResult",
    "ConfigLoader",
    "FieldUpdate",
    "generate_config_schema",
    "load_config",
]
