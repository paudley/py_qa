# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Section-specific configuration merge helpers for :mod:`pyqa.core.config.loader`."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Generic, TypeAlias, TypeVar, cast

from pydantic import BaseModel, ConfigDict, model_validator

from ..models import (
    CleanConfig,
    ConfigError,
    DedupeConfig,
    ExecutionConfig,
    FileDiscoveryConfig,
    GenericValueTypesConfig,
    GenericValueTypesImplication,
    GenericValueTypesRule,
    LicenseConfig,
    OutputConfig,
    QualityConfigSection,
    UpdateConfig,
)
from ..types import ConfigValue
from ..utils import (
    _coerce_iterable,
    _coerce_optional_int,
    _coerce_string_sequence,
    _existing_unique_paths,
    _normalize_min_severity,
    _normalize_output_mode,
    _normalize_tool_filters,
    _unique_paths,
)

ModelScalarUpdate: TypeAlias = ConfigValue | Path | BaseModel
ModelSequenceUpdate: TypeAlias = Sequence[ConfigValue | Path | BaseModel]
ModelMappingUpdate: TypeAlias = Mapping[str, ConfigValue | Path | BaseModel]
ModelUpdateValue: TypeAlias = ModelScalarUpdate | ModelSequenceUpdate | ModelMappingUpdate

SectionName = str
FieldName = str
ModelT = TypeVar("ModelT", bound=BaseModel)

FILE_DISCOVERY_ROOTS_KEY: SectionName = "roots"
FILE_DISCOVERY_EXCLUDES_KEY: SectionName = "excludes"
FILE_DISCOVERY_EXPLICIT_KEY: SectionName = "explicit_files"
FILE_DISCOVERY_LIMIT_KEY: SectionName = "limit_to"
OUTPUT_TOOL_FILTERS_KEY: SectionName = "tool_filters"
OUTPUT_MIN_SEVERITY_KEY: SectionName = "pr_summary_min_severity"
OUTPUT_REPORT_OUT_KEY: SectionName = "report_out"
OUTPUT_SARIF_OUT_KEY: SectionName = "sarif_out"
OUTPUT_PR_SUMMARY_OUT_KEY: SectionName = "pr_summary_out"
EXECUTION_ONLY_KEY: SectionName = "only"
EXECUTION_LANGUAGES_KEY: SectionName = "languages"
EXECUTION_ENABLE_KEY: SectionName = "enable"
LICENSE_ALLOW_ALTERNATE_KEY: SectionName = "allow_alternate_spdx"
LICENSE_EXCEPTIONS_KEY: SectionName = "exceptions"
QUALITY_CHECKS_KEY: SectionName = "checks"
QUALITY_SKIP_GLOBS_KEY: SectionName = "skip_globs"
QUALITY_SCHEMA_TARGETS_KEY: SectionName = "schema_targets"
QUALITY_PROTECTED_BRANCHES_KEY: SectionName = "protected_branches"
CLEAN_PATTERNS_KEY: SectionName = "patterns"
CLEAN_TREES_KEY: SectionName = "trees"
UPDATE_SKIP_PATTERNS_KEY: SectionName = "skip_patterns"
UPDATE_ENABLED_MANAGERS_KEY: SectionName = "enabled_managers"
DEDUPE_PREFER_KEY: SectionName = "dedupe_prefer"
GENERIC_VALUE_TYPES_ENABLED_KEY: SectionName = "enabled"
GENERIC_VALUE_TYPES_RULES_KEY: SectionName = "rules"
GENERIC_VALUE_TYPES_IMPLICATIONS_KEY: SectionName = "implications"


ConfigMapping = Mapping[str, ConfigValue]
SectionDiff = dict[str, ConfigValue]


class PathResolver(BaseModel):
    """Convert path-like values relative to the project root."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_root: Path

    @model_validator(mode="after")
    def _normalise_root(self) -> PathResolver:
        """Return a resolver with an absolute project root.

        Returns:
            PathResolver: Instance with :attr:`project_root` resolved.
        """

        object.__setattr__(self, "project_root", self.project_root.resolve())
        return self

    def resolve(self, value: Path | str) -> Path:
        """Return an absolute path relative to the project root.

        Args:
            value: Path-like object to resolve.

        Returns:
            Path: Absolute path derived from ``value``.
        """

        candidate = value if isinstance(value, Path) else Path(value)
        candidate = candidate.expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.project_root / candidate).resolve()

    def resolve_optional(self, value: Path | str | None) -> Path | None:
        """Resolve ``value`` while preserving ``None`` inputs.

        Args:
            value: Path-like object that may be ``None``.

        Returns:
            Optional absolute path corresponding to ``value``.
        """

        if value is None:
            return None
        return self.resolve(value)

    def resolve_iterable(self, values: Iterable[Path | str]) -> list[Path]:
        """Resolve a collection of path-like values.

        Args:
            values: Iterable of path-like objects to resolve.

        Returns:
            List of absolute paths corresponding to ``values``.
        """

        return [self.resolve(value) for value in values]


def _ensure_optional_path(value: ConfigValue | Path | None, context: str) -> Path | str | None:
    """Return path-like configuration values with validation."""

    if value is None:
        return None
    if isinstance(value, (str, Path)):
        return value
    raise ConfigError(f"{context} must be a path-like string")


def _model_replace(
    instance: ModelT,
    updates: Mapping[str, ModelUpdateValue] | None = None,
) -> ModelT:
    """Return a defensive deep copy of ``instance`` with ``updates`` applied.

    Args:
        instance: Pydantic model instance to clone.
        updates: Mapping of field overrides applied to the clone.

    Returns:
        ModelT: Cloned instance containing requested overrides.
    """

    if not isinstance(instance, BaseModel):  # defensive guard for legacy usage
        raise TypeError("_model_replace expects a Pydantic BaseModel instance")
    return instance.model_copy(update=dict(updates or {}), deep=True)


def _coerce_optional_str_value(
    value: ConfigValue,
    current: str | None,
    context: str,
) -> str | None:
    """Return cleaned string values allowing ``None`` defaults.

    Args:
        value: Raw configuration value.
        current: Existing value preserved when ``value`` is ``None``.
        context: Dot-delimited configuration key for error reporting.

    Returns:
        Normalised string value or ``None``.

    Raises:
        ConfigError: If ``value`` cannot be converted into a string.
    """

    if value is None:
        return current
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    raise ConfigError(f"{context} must be a string")


def _coerce_optional_bool(value: ConfigValue, current: bool, context: str) -> bool:
    """Return cleaned bool values allowing ``None`` defaults.

    Args:
        value: Raw configuration value.
        current: Existing value preserved when ``value`` is ``None``.
        context: Dot-delimited configuration key for error reporting.

    Returns:
        Boolean value recognised by the configuration model.

    Raises:
        ConfigError: If ``value`` cannot be interpreted as a boolean.
    """

    if value is None:
        return current
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{context} must be a boolean")


class _SectionMerger(Generic[ModelT], ABC):
    """Base utilities for section-specific merge implementations."""

    section: SectionName

    def describe_section(self) -> SectionName:
        """Return the section identifier managed by this merger.

        Returns:
            SectionName: Name of the configuration section managed by the merger.
        """

        return self.section

    @abstractmethod
    def merge(self, current: ModelT, raw: ConfigValue) -> tuple[ModelT, SectionDiff]:
        """Return updated section model merged with raw configuration data.

        Args:
            current: Existing configuration model instance.
            raw: Raw section payload sourced from configuration files.

        Returns:
            Tuple containing the merged model and the diff of applied values.
        """

    @staticmethod
    def _ensure_mapping(raw: ConfigValue, section: str) -> ConfigMapping:
        """Return a mapping view of ``raw`` validated for ``section``.

        Args:
            raw: Raw configuration payload.
            section: Name of the section being processed.

        Returns:
            Mapping suitable for structured processing.

        Raises:
            ConfigError: If ``raw`` is not a mapping.
        """
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{section} section must be a table")
        result: dict[str, ConfigValue] = {}
        for key, value in raw.items():
            if not isinstance(key, str):
                raise ConfigError(f"{section} section keys must be strings")
            result[key] = value
        return result

    @staticmethod
    def _diff_model(current: BaseModel, updated: BaseModel) -> SectionDiff:
        """Return a dictionary describing fields changed between models.

        Args:
            current: Baseline Pydantic model instance.
            updated: Updated model instance.

        Returns:
            Mapping containing only the fields that changed.
        """
        current_data = current.model_dump(mode="python")
        updated_data = updated.model_dump(mode="python")
        result: SectionDiff = {}
        for key, value in updated_data.items():
            if current_data.get(key) != value:
                result[key] = value
        return result


class _FileDiscoverySection(_SectionMerger[FileDiscoveryConfig]):
    section = "file_discovery"

    def __init__(self, resolver: PathResolver) -> None:
        """Initialise the merger with a shared path resolver.

        Args:
            resolver: Resolver anchored to the project root.
        """
        self._resolver = resolver

    def merge(
        self,
        current: FileDiscoveryConfig,
        raw: ConfigValue,
    ) -> tuple[FileDiscoveryConfig, SectionDiff]:
        """Return a merged ``file_discovery`` configuration section.

        Args:
            current: Existing file discovery configuration model.
            raw: Raw payload supplied by configuration sources.

        Returns:
            Tuple containing the updated model and diff mapping.
        """

        data = self._ensure_mapping(raw, self.section)
        roots = list(current.roots)
        if FILE_DISCOVERY_ROOTS_KEY in data:
            raw_roots = cast(
                Iterable[Path | str],
                _coerce_iterable(data[FILE_DISCOVERY_ROOTS_KEY], "file_discovery.roots"),
            )
            roots = _unique_paths(self._resolver.resolve_iterable(raw_roots))
        elif not roots:
            roots = [self._resolver.project_root]

        excludes = _unique_paths(current.excludes)
        if FILE_DISCOVERY_EXCLUDES_KEY in data:
            raw_excludes = cast(
                Iterable[Path | str],
                _coerce_iterable(
                    data[FILE_DISCOVERY_EXCLUDES_KEY],
                    "file_discovery.excludes",
                ),
            )
            for resolved in self._resolver.resolve_iterable(raw_excludes):
                candidate = resolved.resolve()
                if candidate not in excludes:
                    excludes.append(candidate)

        explicit_files = _existing_unique_paths(current.explicit_files)
        if FILE_DISCOVERY_EXPLICIT_KEY in data:
            raw_explicit = cast(
                Iterable[Path | str],
                _coerce_iterable(
                    data[FILE_DISCOVERY_EXPLICIT_KEY],
                    "file_discovery.explicit_files",
                ),
            )
            for resolved in self._resolver.resolve_iterable(raw_explicit):
                candidate = resolved.resolve()
                if candidate.exists() and candidate not in explicit_files:
                    explicit_files.append(candidate)

        limit_to = _unique_paths(current.limit_to)
        if FILE_DISCOVERY_LIMIT_KEY in data:
            raw_limits = cast(
                Iterable[Path | str],
                _coerce_iterable(
                    data[FILE_DISCOVERY_LIMIT_KEY],
                    "file_discovery.limit_to",
                ),
            )
            limit_to = _unique_paths(self._resolver.resolve_iterable(raw_limits))

        updates: dict[str, ModelUpdateValue] = {
            "roots": roots,
            "excludes": excludes,
            "explicit_files": explicit_files,
            "paths_from_stdin": data.get("paths_from_stdin", current.paths_from_stdin),
            "changed_only": data.get("changed_only", current.changed_only),
            "diff_ref": data.get("diff_ref", current.diff_ref),
            "include_untracked": data.get("include_untracked", current.include_untracked),
            "base_branch": data.get("base_branch", current.base_branch),
            "pre_commit": data.get("pre_commit", current.pre_commit),
            "respect_gitignore": data.get("respect_gitignore", current.respect_gitignore),
            "limit_to": limit_to,
        }
        updated = _model_replace(current, updates=updates)
        return updated, self._diff_model(current, updated)


class _OutputSection(_SectionMerger[OutputConfig]):
    section = "output"

    def __init__(self, resolver: PathResolver) -> None:
        """Initialise the merger with a shared path resolver.

        Args:
            resolver: Resolver anchored to the project root.
        """
        self._resolver = resolver

    def merge(self, current: OutputConfig, raw: ConfigValue) -> tuple[OutputConfig, SectionDiff]:
        """Return a merged ``output`` configuration section.

        Args:
            current: Existing output configuration model.
            raw: Raw payload supplied by configuration sources.

        Returns:
            Tuple containing the updated model and diff mapping.
        """

        data = self._ensure_mapping(raw, self.section)

        tool_filters = current.tool_filters
        if OUTPUT_TOOL_FILTERS_KEY in data:
            tool_filters = _normalize_tool_filters(
                data[OUTPUT_TOOL_FILTERS_KEY],
                current.tool_filters,
            )

        pr_summary_min_raw = data.get(OUTPUT_MIN_SEVERITY_KEY, current.pr_summary_min_severity)
        pr_summary_min_severity = _normalize_min_severity(str(pr_summary_min_raw))

        pr_summary_raw_value = data.get(OUTPUT_PR_SUMMARY_OUT_KEY)
        pr_summary_out_raw = _ensure_optional_path(
            pr_summary_raw_value if pr_summary_raw_value is not None else current.pr_summary_out,
            "output.pr_summary_out",
        )
        pr_summary_out = self._resolver.resolve_optional(pr_summary_out_raw)

        report_raw_value = data.get(OUTPUT_REPORT_OUT_KEY)
        report_out_raw = _ensure_optional_path(
            report_raw_value if report_raw_value is not None else current.report_out,
            "output.report_out",
        )
        report_out = self._resolver.resolve_optional(report_out_raw)

        sarif_raw_value = data.get(OUTPUT_SARIF_OUT_KEY)
        sarif_out_raw = _ensure_optional_path(
            sarif_raw_value if sarif_raw_value is not None else current.sarif_out,
            "output.sarif_out",
        )
        sarif_out = self._resolver.resolve_optional(sarif_out_raw)

        output_mode_raw = data.get("output", current.output)
        output_mode = _normalize_output_mode(str(output_mode_raw))

        verbose = _coerce_optional_bool(data.get("verbose"), current.verbose, "output.verbose")
        emoji = _coerce_optional_bool(data.get("emoji"), current.emoji, "output.emoji")
        color = _coerce_optional_bool(data.get("color"), current.color, "output.color")
        show_passing = _coerce_optional_bool(
            data.get("show_passing"),
            current.show_passing,
            "output.show_passing",
        )
        show_stats = _coerce_optional_bool(
            data.get("show_stats"),
            current.show_stats,
            "output.show_stats",
        )

        pretty_format_raw = data.get("pretty_format", current.pretty_format)
        if not isinstance(pretty_format_raw, str):
            raise ConfigError("output.pretty_format must be a string")
        pretty_format = pretty_format_raw

        group_by_code = _coerce_optional_bool(
            data.get("group_by_code"),
            current.group_by_code,
            "output.group_by_code",
        )

        report_raw = data.get("report", current.report)
        if report_raw is not None and not isinstance(report_raw, str):
            raise ConfigError("output.report must be null or a string")
        report = report_raw

        report_include_raw = _coerce_optional_bool(
            data.get("report_include_raw"),
            current.report_include_raw,
            "output.report_include_raw",
        )

        pr_summary_limit = _coerce_optional_int(
            data.get("pr_summary_limit"),
            current.pr_summary_limit,
            "output.pr_summary_limit",
        )

        pr_summary_template_raw = data.get("pr_summary_template", current.pr_summary_template)
        if not isinstance(pr_summary_template_raw, str):
            raise ConfigError("output.pr_summary_template must be a string")
        pr_summary_template = pr_summary_template_raw

        gha_annotations = _coerce_optional_bool(
            data.get("gha_annotations"),
            current.gha_annotations,
            "output.gha_annotations",
        )
        annotations_use_json = _coerce_optional_bool(
            data.get("annotations_use_json"),
            current.annotations_use_json,
            "output.annotations_use_json",
        )
        quiet = _coerce_optional_bool(data.get("quiet"), current.quiet, "output.quiet")
        advice = _coerce_optional_bool(data.get("advice"), current.advice, "output.advice")

        updates: dict[str, ModelUpdateValue] = {
            "verbose": verbose,
            "emoji": emoji,
            "color": color,
            "show_passing": show_passing,
            "show_stats": show_stats,
            "output": output_mode,
            "pretty_format": pretty_format,
            "group_by_code": group_by_code,
            "report": report,
            "report_out": report_out,
            "report_include_raw": report_include_raw,
            "sarif_out": sarif_out,
            "pr_summary_out": pr_summary_out,
            "pr_summary_limit": pr_summary_limit,
            "pr_summary_min_severity": pr_summary_min_severity,
            "pr_summary_template": pr_summary_template,
            "gha_annotations": gha_annotations,
            "annotations_use_json": annotations_use_json,
            "quiet": quiet,
            "tool_filters": tool_filters,
            "advice": advice,
        }
        updated = _model_replace(current, updates=updates)

        if updated.show_passing and updated.quiet:
            updated = _model_replace(updated, updates={"show_passing": False})

        return updated, self._diff_model(current, updated)


class _ExecutionSection(_SectionMerger[ExecutionConfig]):
    section = "execution"

    def __init__(self, resolver: PathResolver) -> None:
        """Initialise the merger with a shared path resolver.

        Args:
            resolver: Resolver anchored to the project root.
        """
        self._resolver = resolver

    def merge(self, current: ExecutionConfig, raw: ConfigValue) -> tuple[ExecutionConfig, SectionDiff]:
        """Return a merged ``execution`` configuration section.

        Args:
            current: Existing execution configuration model.
            raw: Raw payload supplied by configuration sources.

        Returns:
            Tuple containing the updated model and diff mapping.
        """

        data = self._ensure_mapping(raw, self.section)

        cache_dir = current.cache_dir
        cache_dir_value = data.get("cache_dir")
        if cache_dir_value is not None:
            if not isinstance(cache_dir_value, (Path, str)):
                raise ConfigError("execution.cache_dir must be a path or string")
            cache_dir = self._resolver.resolve(cache_dir_value)

        jobs = _coerce_optional_int(data.get("jobs"), current.jobs, "execution.jobs")
        bail = _coerce_optional_bool(data.get("bail"), current.bail, "execution.bail")
        if bail:
            jobs = 1

        only = (
            _coerce_string_sequence(data[EXECUTION_ONLY_KEY], "execution.only")
            if EXECUTION_ONLY_KEY in data
            else list(current.only)
        )
        languages = (
            _coerce_string_sequence(data[EXECUTION_LANGUAGES_KEY], "execution.languages")
            if EXECUTION_LANGUAGES_KEY in data
            else list(current.languages)
        )
        enable = (
            _coerce_string_sequence(data[EXECUTION_ENABLE_KEY], "execution.enable")
            if EXECUTION_ENABLE_KEY in data
            else list(current.enable)
        )

        updates: dict[str, ModelUpdateValue] = {
            "only": only,
            "languages": languages,
            "enable": enable,
            "strict": _coerce_optional_bool(data.get("strict"), current.strict, "execution.strict"),
            "jobs": jobs,
            "fix_only": _coerce_optional_bool(data.get("fix_only"), current.fix_only, "execution.fix_only"),
            "check_only": _coerce_optional_bool(data.get("check_only"), current.check_only, "execution.check_only"),
            "force_all": _coerce_optional_bool(data.get("force_all"), current.force_all, "execution.force_all"),
            "respect_config": _coerce_optional_bool(
                data.get("respect_config"),
                current.respect_config,
                "execution.respect_config",
            ),
            "cache_enabled": _coerce_optional_bool(
                data.get("cache_enabled"),
                current.cache_enabled,
                "execution.cache_enabled",
            ),
            "cache_dir": cache_dir,
            "bail": bail,
            "use_local_linters": _coerce_optional_bool(
                data.get("use_local_linters"),
                current.use_local_linters,
                "execution.use_local_linters",
            ),
        }
        updated = _model_replace(current, updates=updates)
        return updated, self._diff_model(current, updated)


class _LicenseSection(_SectionMerger[LicenseConfig]):
    section = "license"

    def merge(self, current: LicenseConfig, raw: ConfigValue) -> tuple[LicenseConfig, SectionDiff]:
        """Return a merged ``license`` configuration section.

        Args:
            current: Existing license configuration model.
            raw: Raw payload supplied by configuration sources.

        Returns:
            Tuple containing the updated model and diff mapping.
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

        updates: dict[str, ModelUpdateValue] = {
            "spdx": spdx,
            "notice": notice,
            "copyright": copyright_value,
            "year": year,
            "require_spdx": require_spdx,
            "require_notice": require_notice,
            "allow_alternate_spdx": allow_alternate,
            "exceptions": exceptions,
        }
        updated = _model_replace(current, updates=updates)
        return updated, self._diff_model(current, updated)


class _QualitySection(_SectionMerger[QualityConfigSection]):
    section = "quality"

    def __init__(self, resolver: PathResolver) -> None:
        """Initialise the merger with a shared path resolver.

        Args:
            resolver: Resolver anchored to the project root.
        """
        self._resolver = resolver

    def merge(
        self,
        current: QualityConfigSection,
        raw: ConfigValue,
    ) -> tuple[QualityConfigSection, SectionDiff]:
        """Return a merged ``quality`` configuration section.

        Args:
            current: Existing quality configuration model.
            raw: Raw payload supplied by configuration sources.

        Returns:
            Tuple containing the updated model and diff mapping.
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

        updates: dict[str, ModelUpdateValue] = {
            "checks": checks,
            "skip_globs": skip_globs,
            "schema_targets": schema_targets,
            "warn_file_size": warn_file_size,
            "max_file_size": max_file_size,
            "protected_branches": protected_branches,
        }
        updated = _model_replace(current, updates=updates)
        return updated, self._diff_model(current, updated)

    def _merge_schema_targets(
        self,
        raw: ConfigValue,
        current: Sequence[Path],
    ) -> list[Path]:
        """Return merged schema targets using path resolution.

        Args:
            raw: Raw schema target payload from configuration files.
            current: Existing schema target list.

        Returns:
            List of resolved schema target paths.

        Raises:
            ConfigError: If ``raw`` does not represent a sequence of paths.
        """
        if raw is None:
            return list(current)
        if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
            raise ConfigError("quality.schema_targets must be an array of paths")
        resolved: list[Path] = []
        for entry in raw:
            if not isinstance(entry, (str, Path)):
                raise ConfigError("quality.schema_targets entries must be paths")
            resolved.append(self._resolver.resolve(entry))
        return resolved


class _GenericValueTypesSection(_SectionMerger[GenericValueTypesConfig]):
    """Merge overrides for the ``generic_value_types`` configuration section."""

    section = "generic_value_types"

    def merge(
        self,
        current: GenericValueTypesConfig,
        raw: ConfigValue,
    ) -> tuple[GenericValueTypesConfig, SectionDiff]:
        """Return a merged ``generic_value_types`` configuration section.

        Args:
            current: Existing generic value types configuration model.
            raw: Raw payload supplied by configuration sources.

        Returns:
            Tuple containing the updated model and diff mapping.
        """
        data = self._ensure_mapping(raw, self.section)

        enabled_raw = data.get(GENERIC_VALUE_TYPES_ENABLED_KEY, current.enabled)
        if not isinstance(enabled_raw, bool):
            raise ConfigError("generic_value_types.enabled must be a boolean")

        rules = current.rules
        if GENERIC_VALUE_TYPES_RULES_KEY in data:
            raw_rules = data[GENERIC_VALUE_TYPES_RULES_KEY]
            if raw_rules is None:
                rules = ()
            elif isinstance(raw_rules, Sequence):
                rules = tuple(GenericValueTypesRule.model_validate(rule) for rule in raw_rules)
            else:
                raise ConfigError("generic_value_types.rules must be an array")

        implications = current.implications
        if GENERIC_VALUE_TYPES_IMPLICATIONS_KEY in data:
            raw_implications = data[GENERIC_VALUE_TYPES_IMPLICATIONS_KEY]
            if raw_implications is None:
                implications = ()
            elif isinstance(raw_implications, Sequence):
                implications = tuple(GenericValueTypesImplication.model_validate(entry) for entry in raw_implications)
            else:
                raise ConfigError("generic_value_types.implications must be an array")

        updates: dict[str, ModelUpdateValue] = {
            "enabled": enabled_raw,
            "rules": rules,
            "implications": implications,
        }
        updated = _model_replace(current, updates=updates)
        return updated, self._diff_model(current, updated)


class _CleanSection(_SectionMerger[CleanConfig]):
    section = "clean"

    def merge(self, current: CleanConfig, raw: ConfigValue) -> tuple[CleanConfig, SectionDiff]:
        """Return a merged ``clean`` configuration section.

        Args:
            current: Existing clean configuration model.
            raw: Raw payload supplied by configuration sources.

        Returns:
            Tuple containing the updated model and diff mapping.
        """

        data = self._ensure_mapping(raw, self.section)

        patterns = list(current.patterns)
        if CLEAN_PATTERNS_KEY in data:
            patterns = _coerce_string_sequence(data[CLEAN_PATTERNS_KEY], "clean.patterns")

        trees = list(current.trees)
        if CLEAN_TREES_KEY in data:
            trees = _coerce_string_sequence(data[CLEAN_TREES_KEY], "clean.trees")

        updated = _model_replace(current, updates={"patterns": patterns, "trees": trees})
        return updated, self._diff_model(current, updated)


class _UpdateSection(_SectionMerger[UpdateConfig]):
    section = "update"

    def merge(self, current: UpdateConfig, raw: ConfigValue) -> tuple[UpdateConfig, SectionDiff]:
        """Return a merged ``update`` configuration section.

        Args:
            current: Existing update configuration model.
            raw: Raw payload supplied by configuration sources.

        Returns:
            Tuple containing the updated model and diff mapping.
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

        updates: dict[str, ModelUpdateValue] = {
            "skip_patterns": skip_patterns,
            "enabled_managers": enabled_managers,
        }
        updated = _model_replace(current, updates=updates)
        return updated, self._diff_model(current, updated)


class _DedupeSection(_SectionMerger[DedupeConfig]):
    section = "dedupe"

    def merge(self, current: DedupeConfig, raw: ConfigValue) -> tuple[DedupeConfig, SectionDiff]:
        """Return a merged ``dedupe`` configuration section.

        Args:
            current: Existing dedupe configuration model.
            raw: Raw payload supplied by configuration sources.

        Returns:
            Tuple containing the updated model and diff mapping.
        """

        data = self._ensure_mapping(raw, self.section)
        dedupe_prefer = list(current.dedupe_prefer)
        if DEDUPE_PREFER_KEY in data:
            dedupe_prefer = _coerce_string_sequence(data[DEDUPE_PREFER_KEY], "dedupe.dedupe_prefer")

        updates: dict[str, ModelUpdateValue] = {
            "dedupe": _coerce_optional_bool(data.get("dedupe"), current.dedupe, "dedupe.dedupe"),
            "dedupe_by": _coerce_optional_str_value(
                data.get("dedupe_by"),
                current.dedupe_by,
                "dedupe.dedupe_by",
            ),
            "dedupe_prefer": dedupe_prefer,
            "dedupe_line_fuzz": _coerce_optional_int(
                data.get("dedupe_line_fuzz"),
                current.dedupe_line_fuzz,
                "dedupe.dedupe_line_fuzz",
            ),
            "dedupe_same_file_only": _coerce_optional_bool(
                data.get("dedupe_same_file_only"),
                current.dedupe_same_file_only,
                "dedupe.dedupe_same_file_only",
            ),
        }
        updated = _model_replace(current, updates=updates)
        return updated, self._diff_model(current, updated)


def build_section_mergers(resolver: PathResolver) -> tuple[tuple[str, _SectionMerger[BaseModel]], ...]:
    """Return configured section mergers keyed by configuration attribute.

    Args:
        resolver: Resolver anchored to the project root.

    Returns:
        Tuple of section identifiers paired with their merger implementations.
    """

    mergers: tuple[tuple[str, _SectionMerger[BaseModel]], ...] = cast(
        tuple[tuple[str, _SectionMerger[BaseModel]], ...],
        (
            ("file_discovery", _FileDiscoverySection(resolver)),
            ("output", _OutputSection(resolver)),
            ("execution", _ExecutionSection(resolver)),
            ("dedupe", _DedupeSection()),
            ("license", _LicenseSection()),
            ("quality", _QualitySection(resolver)),
            ("generic_value_types", _GenericValueTypesSection()),
            ("clean", _CleanSection()),
            ("update", _UpdateSection()),
        ),
    )
    return mergers


__all__ = [
    "CLEAN_PATTERNS_KEY",
    "CLEAN_TREES_KEY",
    "DEDUPE_PREFER_KEY",
    "EXECUTION_ENABLE_KEY",
    "EXECUTION_LANGUAGES_KEY",
    "EXECUTION_ONLY_KEY",
    "FieldName",
    "FILE_DISCOVERY_EXCLUDES_KEY",
    "FILE_DISCOVERY_EXPLICIT_KEY",
    "FILE_DISCOVERY_LIMIT_KEY",
    "FILE_DISCOVERY_ROOTS_KEY",
    "LICENSE_ALLOW_ALTERNATE_KEY",
    "LICENSE_EXCEPTIONS_KEY",
    "ModelT",
    "OUTPUT_MIN_SEVERITY_KEY",
    "OUTPUT_PR_SUMMARY_OUT_KEY",
    "OUTPUT_REPORT_OUT_KEY",
    "OUTPUT_SARIF_OUT_KEY",
    "OUTPUT_TOOL_FILTERS_KEY",
    "PathResolver",
    "QUALITY_CHECKS_KEY",
    "QUALITY_PROTECTED_BRANCHES_KEY",
    "QUALITY_SCHEMA_TARGETS_KEY",
    "QUALITY_SKIP_GLOBS_KEY",
    "SectionName",
    "GENERIC_VALUE_TYPES_ENABLED_KEY",
    "GENERIC_VALUE_TYPES_RULES_KEY",
    "GENERIC_VALUE_TYPES_IMPLICATIONS_KEY",
    "UPDATE_ENABLED_MANAGERS_KEY",
    "UPDATE_SKIP_PATTERNS_KEY",
    "_SectionMerger",
    "_coerce_optional_bool",
    "_coerce_optional_str_value",
    "_model_replace",
    "build_section_mergers",
]
