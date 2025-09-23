# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Config loading utilities with layered precedence and traceability."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    Mapping,
    MutableMapping,
    Protocol,
    Sequence,
    TypeVar,
    cast,
)

try:  # Python 3.11+ includes tomllib in the stdlib. Fallbacks unsupported.
    import tomllib  # type: ignore[attr-defined]
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


class ConfigSource(Protocol):
    """Provide configuration fragments and metadata about their origin."""

    name: str

    def load(self) -> Mapping[str, Any]:
        """Return a mapping of configuration overrides."""
        raise NotImplementedError


class DefaultConfigSource:
    """Return the built-in defaults as a configuration fragment."""

    name = "defaults"

    def load(self) -> Mapping[str, Any]:
        return Config().to_dict()


class TomlConfigSource:
    """Load configuration data from a TOML document with include support."""

    def __init__(
        self,
        path: Path,
        *,
        name: str | None = None,
        include_key: str = "include",
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
            raise ConfigError(
                "Circular include detected: "
                + " -> ".join(str(entry) for entry in stack + (path,))
            )
        resolved = path.resolve()
        stat = resolved.stat()
        cache_key = (resolved, stat.st_mtime_ns)
        cached = _TOML_CACHE.get(cache_key)
        if cached is not None:
            data = copy.deepcopy(cached)
        else:
            with resolved.open("rb") as handle:
                data = tomllib.load(handle)
            _TOML_CACHE[cache_key] = copy.deepcopy(data)
        if not isinstance(data, MutableMapping):
            raise ConfigError(f"Configuration at {path} must be a table")
        document: Dict[str, Any] = dict(data)
        includes = document.pop(self._include_key, None)
        merged: Dict[str, Any] = {}
        for include_path in self._coerce_includes(includes, path.parent):
            fragment = self._load(include_path, stack + (path,))
            merged = _deep_merge(merged, fragment)
        merged = _deep_merge(merged, document)
        return _expand_env(merged, self._env)

    def _coerce_includes(self, raw: Any, base_dir: Path) -> Iterable[Path]:
        if raw is None:
            return []
        if isinstance(raw, (str, Path)):
            raw = [raw]
        if not isinstance(raw, Iterable) or isinstance(raw, (bytes, str)):
            raise ConfigError(
                f"Include declarations in {self._root_path} must be a string or list"
            )
        paths: list[Path] = []
        for entry in raw:
            if not isinstance(entry, (str, Path)):
                raise ConfigError("Include entries must be strings or paths")
            candidate = Path(entry).expanduser()
            if not candidate.is_absolute():
                candidate = (base_dir / candidate).resolve()
            paths.append(candidate)
        return paths


class PyProjectConfigSource(TomlConfigSource):
    """Read configuration from ``[tool.pyqa]`` within ``pyproject.toml``."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, name=str(path))

    def load(self) -> Mapping[str, Any]:
        data = super().load()
        tool = data.get("tool")
        if not tool:
            return {}
        pyqa_data = tool.get("pyqa") if isinstance(tool, Mapping) else None
        if not isinstance(pyqa_data, Mapping):
            return {}
        return _normalise_pyproject_payload(dict(pyqa_data))


class PathResolver(BaseModel):
    """Convert path-like values relative to the project root."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_root: Path

    @model_validator(mode="after")
    def _normalise_root(self) -> "PathResolver":
        object.__setattr__(self, "project_root", self.project_root.resolve())
        return self

    def resolve(self, value: Path | str) -> Path:
        candidate = value if isinstance(value, Path) else Path(value)
        candidate = candidate.expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.project_root / candidate).resolve()

    def resolve_optional(self, value: Path | str | None) -> Path | None:
        if value is None:
            return None
        return self.resolve(value)

    def resolve_iterable(self, values: Iterable[Path | str]) -> list[Path]:
        return [self.resolve(value) for value in values]


class FieldUpdate(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    section: SectionName
    field: FieldName
    source: str
    value: Any


class ConfigLoadResult(BaseModel):
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
    ) -> "ConfigLoader":
        """Build a loader with default tiered sources."""

        root = project_root.resolve()
        home_config = (
            user_config if user_config is not None else Path.home() / ".py_qa.toml"
        )
        project_file = (
            project_config if project_config is not None else root / ".py_qa.toml"
        )
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
        return self.load_with_trace(strict=strict).config

    def load_with_trace(self, *, strict: bool = False) -> ConfigLoadResult:
        config = Config().model_copy(deep=True)
        updates: list[FieldUpdate] = []
        warnings: list[str] = []
        snapshots: dict[str, dict[str, Any]] = {}
        for source in self._sources:
            fragment = source.load()
            if not fragment:
                continue
            normalised = _normalise_fragment(fragment)
            if not normalised:
                continue
            config, changed, new_warnings = self._merger.apply(
                config, normalised, source.name
            )
            updates.extend(changed)
            warnings.extend(new_warnings)
            snapshots[source.name] = _config_to_snapshot(config)
        auto_updates = _auto_discover_tool_settings(
            config,
            self._project_root,
        )
        if auto_updates:
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
        self._resolver = resolver
        self._file_section = _FileDiscoverySection(resolver)
        self._output_section = _OutputSection(resolver)
        self._execution_section = _ExecutionSection(resolver)
        self._dedupe_section = _DedupeSection()
        self._license_section = _LicenseSection()
        self._quality_section = _QualitySection(resolver)
        self._clean_section = _CleanSection()
        self._update_section = _UpdateSection()

    def apply(
        self, config: Config, data: Mapping[str, Any], source: str
    ) -> tuple[Config, list[FieldUpdate], list[str]]:
        updates: list[FieldUpdate] = []
        warnings: list[str] = []

        file_config, file_updates = self._file_section.merge(
            config.file_discovery, data.get("file_discovery")
        )
        updates.extend(
            FieldUpdate(
                section="file_discovery", field=field, source=source, value=value
            )
            for field, value in file_updates.items()
        )

        output_config, output_updates = self._output_section.merge(
            config.output, data.get("output")
        )
        updates.extend(
            FieldUpdate(section="output", field=field, source=source, value=value)
            for field, value in output_updates.items()
        )

        execution_config, execution_updates = self._execution_section.merge(
            config.execution, data.get("execution")
        )
        updates.extend(
            FieldUpdate(section="execution", field=field, source=source, value=value)
            for field, value in execution_updates.items()
        )

        dedupe_config, dedupe_updates = self._dedupe_section.merge(
            config.dedupe, data.get("dedupe")
        )
        updates.extend(
            FieldUpdate(section="dedupe", field=field, source=source, value=value)
            for field, value in dedupe_updates.items()
        )

        license_config, license_updates = self._license_section.merge(
            config.license, data.get("license")
        )
        updates.extend(
            FieldUpdate(section="license", field=field, source=source, value=value)
            for field, value in license_updates.items()
        )

        quality_config, quality_updates = self._quality_section.merge(
            config.quality, data.get("quality")
        )
        updates.extend(
            FieldUpdate(section="quality", field=field, source=source, value=value)
            for field, value in quality_updates.items()
        )

        clean_config, clean_updates = self._clean_section.merge(
            config.clean, data.get("clean")
        )
        updates.extend(
            FieldUpdate(section="clean", field=field, source=source, value=value)
            for field, value in clean_updates.items()
        )

        update_config, update_updates = self._update_section.merge(
            config.update, data.get("update")
        )
        updates.extend(
            FieldUpdate(section="update", field=field, source=source, value=value)
            for field, value in update_updates.items()
        )

        tool_settings, tool_updates, tool_warnings = _merge_tool_settings(
            config.tool_settings, data.get("tools"), source
        )
        warnings.extend(tool_warnings)
        updates.extend(
            FieldUpdate(section="tool_settings", field=tool, source=source, value=value)
            for tool, value in tool_updates.items()
        )

        severity_rules = _merge_severity_rules(
            config.severity_rules, data.get("severity_rules")
        )
        if severity_rules != config.severity_rules:
            updates.append(
                FieldUpdate(
                    section="root",
                    field="severity_rules",
                    source=source,
                    value=list(severity_rules),
                )
            )

        merged = _model_replace(
            config,
            file_discovery=file_config,
            output=output_config,
            execution=execution_config,
            dedupe=dedupe_config,
            severity_rules=severity_rules,
            tool_settings=tool_settings,
            license=license_config,
            quality=quality_config,
            clean=clean_config,
            update=update_config,
        )
        return merged, updates, warnings


class _SectionMerger:
    """Base utilities for section-specific merge implementations."""

    section: SectionName

    @staticmethod
    def _ensure_mapping(raw: Any, section: str) -> Mapping[str, Any]:
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{section} section must be a table")
        return raw

    @staticmethod
    def _diff_model(current: BaseModel, updated: BaseModel) -> Dict[str, Any]:
        current_data = current.model_dump(mode="python")
        updated_data = updated.model_dump(mode="python")
        result: Dict[str, Any] = {}
        for key, value in updated_data.items():
            if current_data.get(key) != value:
                result[key] = value
        return result


class _FileDiscoverySection(_SectionMerger):
    section = "file_discovery"

    def __init__(self, resolver: PathResolver) -> None:
        self._resolver = resolver

    def merge(
        self, current: FileDiscoveryConfig, raw: Any
    ) -> tuple[FileDiscoveryConfig, Dict[str, Any]]:
        data = self._ensure_mapping(raw, self.section)
        roots = list(current.roots)
        if "roots" in data:
            raw_roots = _coerce_iterable(data["roots"], "file_discovery.roots")
            roots = _unique_paths(self._resolver.resolve_iterable(raw_roots))
        elif not roots:
            roots = [self._resolver.project_root]

        excludes = _unique_paths(current.excludes)
        if "excludes" in data:
            raw_excludes = _coerce_iterable(data["excludes"], "file_discovery.excludes")
            for resolved in self._resolver.resolve_iterable(raw_excludes):
                candidate = resolved.resolve()
                if candidate not in excludes:
                    excludes.append(candidate)

        explicit_files = _existing_unique_paths(current.explicit_files)
        if "explicit_files" in data:
            raw_explicit = _coerce_iterable(
                data["explicit_files"], "file_discovery.explicit_files"
            )
            for resolved in self._resolver.resolve_iterable(raw_explicit):
                candidate = resolved.resolve()
                if candidate.exists() and candidate not in explicit_files:
                    explicit_files.append(candidate)

        limit_to = _unique_paths(current.limit_to)
        if "limit_to" in data:
            raw_limits = _coerce_iterable(data["limit_to"], "file_discovery.limit_to")
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

    def merge(
        self, current: OutputConfig, raw: Any
    ) -> tuple[OutputConfig, Dict[str, Any]]:
        data = self._ensure_mapping(raw, self.section)
        tool_filters = {
            tool: patterns.copy() for tool, patterns in current.tool_filters.items()
        }
        if "tool_filters" in data:
            tool_filters = _normalize_tool_filters(
                data["tool_filters"], current.tool_filters
            )

        pr_summary_out = self._resolver.resolve_optional(
            data.get("pr_summary_out", current.pr_summary_out)
        )
        report_out = self._resolver.resolve_optional(
            data.get("report_out", current.report_out)
        )
        sarif_out = self._resolver.resolve_optional(
            data.get("sarif_out", current.sarif_out)
        )

        output_mode = data.get("output", current.output)
        if not isinstance(output_mode, str):
            raise ConfigError("output.mode must be a string")
        normalized_output = _normalize_output_mode(output_mode)

        pr_summary_min = data.get(
            "pr_summary_min_severity", current.pr_summary_min_severity
        )
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
            report_include_raw=data.get(
                "report_include_raw", current.report_include_raw
            ),
            sarif_out=sarif_out,
            pr_summary_out=pr_summary_out,
            pr_summary_limit=data.get("pr_summary_limit", current.pr_summary_limit),
            pr_summary_min_severity=normalized_min,
            pr_summary_template=data.get(
                "pr_summary_template", current.pr_summary_template
            ),
            gha_annotations=data.get("gha_annotations", current.gha_annotations),
            annotations_use_json=data.get(
                "annotations_use_json", current.annotations_use_json
            ),
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

    def merge(
        self, current: ExecutionConfig, raw: Any
    ) -> tuple[ExecutionConfig, Dict[str, Any]]:
        data = self._ensure_mapping(raw, self.section)
        cache_dir_value = data.get("cache_dir", current.cache_dir)
        cache_dir = (
            self._resolver.resolve(cache_dir_value)
            if cache_dir_value is not None
            else current.cache_dir
        )

        jobs = data.get("jobs", current.jobs)
        bail = data.get("bail", current.bail)
        if bail:
            jobs = 1

        only = (
            list(_coerce_iterable(data["only"], "execution.only"))
            if "only" in data
            else list(current.only)
        )
        languages = (
            list(_coerce_iterable(data["languages"], "execution.languages"))
            if "languages" in data
            else list(current.languages)
        )
        enable = (
            list(_coerce_iterable(data["enable"], "execution.enable"))
            if "enable" in data
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

    def merge(
        self, current: LicenseConfig, raw: Any
    ) -> tuple[LicenseConfig, Dict[str, Any]]:
        data = self._ensure_mapping(raw, self.section)

        spdx = _coerce_optional_str_value(
            data.get("spdx"), current.spdx, "license.spdx"
        )
        notice = _coerce_optional_str_value(
            data.get("notice"), current.notice, "license.notice"
        )
        copyright_value = _coerce_optional_str_value(
            data.get("copyright"), current.copyright, "license.copyright"
        )
        year = _coerce_optional_str_value(
            data.get("year"), current.year, "license.year"
        )

        require_spdx = _coerce_optional_bool(
            data.get("require_spdx"), current.require_spdx, "license.require_spdx"
        )
        require_notice = _coerce_optional_bool(
            data.get("require_notice"), current.require_notice, "license.require_notice"
        )

        allow_alternate = list(current.allow_alternate_spdx)
        if "allow_alternate_spdx" in data:
            allow_alternate = _coerce_string_sequence(
                data["allow_alternate_spdx"], "license.allow_alternate_spdx"
            )

        exceptions = list(current.exceptions)
        if "exceptions" in data:
            exceptions = _coerce_string_sequence(
                data["exceptions"], "license.exceptions"
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
        self, current: QualityConfigSection, raw: Any
    ) -> tuple[QualityConfigSection, Dict[str, Any]]:
        data = self._ensure_mapping(raw, self.section)

        checks = list(current.checks)
        if "checks" in data:
            checks = _coerce_string_sequence(data["checks"], "quality.checks")

        skip_globs = list(current.skip_globs)
        if "skip_globs" in data:
            skip_globs = _coerce_string_sequence(
                data["skip_globs"], "quality.skip_globs"
            )

        schema_targets = current.schema_targets
        if "schema_targets" in data:
            raw_targets = _coerce_iterable(
                data["schema_targets"], "quality.schema_targets"
            )
            resolved: list[Path] = []
            seen: set[Path] = set()
            for entry in raw_targets:
                if not isinstance(entry, (str, Path)):
                    raise ConfigError("quality.schema_targets entries must be paths")
                candidate = self._resolver.resolve(entry)
                if candidate not in seen:
                    seen.add(candidate)
                    resolved.append(candidate)
            schema_targets = resolved

        warn_file_size = _coerce_optional_int(
            data.get("warn_file_size"), current.warn_file_size, "quality.warn_file_size"
        )
        max_file_size = _coerce_optional_int(
            data.get("max_file_size"), current.max_file_size, "quality.max_file_size"
        )

        protected_branches = list(current.protected_branches)
        if "protected_branches" in data:
            protected_branches = _coerce_string_sequence(
                data["protected_branches"], "quality.protected_branches"
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


class _CleanSection(_SectionMerger):
    section = "clean"

    def merge(
        self, current: CleanConfig, raw: Any
    ) -> tuple[CleanConfig, Dict[str, Any]]:
        data = self._ensure_mapping(raw, self.section)
        patterns = list(current.patterns)
        if "patterns" in data:
            patterns = _coerce_string_sequence(data["patterns"], "clean.patterns")

        trees = list(current.trees)
        if "trees" in data:
            trees = _coerce_string_sequence(data["trees"], "clean.trees")

        updated = _model_replace(current, patterns=patterns, trees=trees)
        return updated, self._diff_model(current, updated)


class _UpdateSection(_SectionMerger):
    section = "update"

    def merge(
        self, current: UpdateConfig, raw: Any
    ) -> tuple[UpdateConfig, Dict[str, Any]]:
        data = self._ensure_mapping(raw, self.section)

        skip_patterns = list(current.skip_patterns)
        if "skip_patterns" in data:
            skip_patterns = _coerce_string_sequence(
                data["skip_patterns"], "update.skip_patterns"
            )

        enabled_managers = list(current.enabled_managers)
        if "enabled_managers" in data:
            enabled_managers = _coerce_string_sequence(
                data["enabled_managers"], "update.enabled_managers"
            )

        updated = _model_replace(
            current,
            skip_patterns=skip_patterns,
            enabled_managers=enabled_managers,
        )
        return updated, self._diff_model(current, updated)


class _DedupeSection(_SectionMerger):
    section = "dedupe"

    def merge(
        self, current: DedupeConfig, raw: Any
    ) -> tuple[DedupeConfig, Dict[str, Any]]:
        data = self._ensure_mapping(raw, self.section)
        updated = _model_replace(
            current,
            dedupe=data.get("dedupe", current.dedupe),
            dedupe_by=data.get("dedupe_by", current.dedupe_by),
            dedupe_prefer=list(data.get("dedupe_prefer", current.dedupe_prefer)),
            dedupe_line_fuzz=data.get("dedupe_line_fuzz", current.dedupe_line_fuzz),
            dedupe_same_file_only=data.get(
                "dedupe_same_file_only", current.dedupe_same_file_only
            ),
        )
        return updated, self._diff_model(current, updated)


def _merge_severity_rules(current: list[str], raw: Any) -> list[str]:
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
    result: dict[str, dict[str, Any]] = {
        tool: dict(settings) for tool, settings in current.items()
    }
    if raw is None:
        return result, {}, []
    if not isinstance(raw, Mapping):
        raise ConfigError("tools section must be a table")
    updates: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for tool, value in raw.items():
        if not isinstance(value, Mapping):
            raise ConfigError(f"tools.{tool} section must be a table")
        schema = TOOL_SETTING_SCHEMA.get(tool)
        if schema is None:
            warnings.append(f"[{source}] Unknown tool '{tool}' in tool settings")
        existing = result.get(tool, {})
        merged = _deep_merge(existing, value)
        if merged != existing:
            result[tool] = merged
            updates[tool] = merged
        if schema:
            for key in value.keys():
                if key not in schema:
                    warnings.append(
                        f"[{source}] Unknown option '{key}' for tool '{tool}' in tool settings"
                    )
    return result, updates, warnings


def _coerce_optional_str_value(
    value: Any, current: str | None, context: str
) -> str | None:
    if value is None:
        return current
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    raise ConfigError(f"{context} must be a string")


def _coerce_optional_bool(value: Any, current: bool, context: str) -> bool:
    if value is None:
        return current
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{context} must be a boolean")


def _config_to_snapshot(config: Config) -> dict[str, Any]:
    snapshot = config.to_dict()
    tools = snapshot.pop("tools", {})
    snapshot["tool_settings"] = tools
    return snapshot


def _auto_discover_tool_settings(config: Config, root: Path) -> list[FieldUpdate]:
    updates: list[FieldUpdate] = []
    for tool, filenames in AUTO_TOOL_CONFIG_FILES.items():
        existing = config.tool_settings.get(tool)
        current_settings = dict(existing) if existing else {}
        if "config" in current_settings:
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
        current_settings["config"] = selected
        config.tool_settings[tool] = current_settings
        updates.append(
            FieldUpdate(
                section="tool_settings",
                field=tool,
                source="auto",
                value=dict(current_settings),
            )
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


ModelT = TypeVar("ModelT", bound=BaseModel)


def _model_replace(instance: ModelT, **updates: Any) -> ModelT:
    if not isinstance(instance, BaseModel):  # defensive guard for legacy usage
        raise TypeError("_model_replace expects a Pydantic BaseModel instance")
    return cast(ModelT, instance.model_copy(update=updates, deep=True))


_TOML_CACHE: dict[tuple[Path, int], Mapping[str, Any]] = {}


__all__ = [
    "ConfigLoader",
    "ConfigLoadResult",
    "FieldUpdate",
    "load_config",
    "generate_config_schema",
]
