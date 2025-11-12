# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Section-specific configuration merge helpers for :mod:`pyqa.core.config.loader`."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel

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
from .constants import (
    CLEAN_PATTERNS_KEY,
    CLEAN_TREES_KEY,
    DEDUPE_PREFER_KEY,
    EXECUTION_ENABLE_KEY,
    EXECUTION_LANGUAGES_KEY,
    EXECUTION_ONLY_KEY,
    FILE_DISCOVERY_EXCLUDES_KEY,
    FILE_DISCOVERY_EXPLICIT_KEY,
    FILE_DISCOVERY_LIMIT_KEY,
    FILE_DISCOVERY_ROOTS_KEY,
    GENERIC_VALUE_TYPES_ENABLED_KEY,
    GENERIC_VALUE_TYPES_IMPLICATIONS_KEY,
    GENERIC_VALUE_TYPES_RULES_KEY,
    LICENSE_ALLOW_ALTERNATE_KEY,
    LICENSE_EXCEPTIONS_KEY,
    OUTPUT_MIN_SEVERITY_KEY,
    OUTPUT_PR_SUMMARY_OUT_KEY,
    OUTPUT_REPORT_OUT_KEY,
    OUTPUT_SARIF_OUT_KEY,
    OUTPUT_TOOL_FILTERS_KEY,
    QUALITY_CHECKS_KEY,
    QUALITY_PROTECTED_BRANCHES_KEY,
    QUALITY_SCHEMA_TARGETS_KEY,
    QUALITY_SKIP_GLOBS_KEY,
    UPDATE_ENABLED_MANAGERS_KEY,
    UPDATE_SKIP_PATTERNS_KEY,
)
from .merge_utils import (
    ModelUpdateValue,
    PathResolver,
    SectionDiff,
    _coerce_optional_bool,
    _coerce_optional_str_value,
    _ensure_optional_path,
    _model_replace,
    _SectionMerger,
)


class _FileDiscoverySection(_SectionMerger[FileDiscoveryConfig]):
    """Handle merges for file discovery configuration sections."""

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
        roots = self._merge_roots(data, current)
        excludes = self._merge_excludes(data, current)
        explicit_files = self._merge_explicit_files(data, current)
        limit_to = self._merge_limit_to(data, current)
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

    def _merge_roots(
        self,
        data: Mapping[str, ConfigValue],
        current: FileDiscoveryConfig,
    ) -> list[Path]:
        """Merge root paths for the file discovery section.

        Args:
            data: Mapping of raw section values.
            current: Existing file discovery configuration.

        Returns:
            List of resolved root paths with fallbacks applied.

        """

        if FILE_DISCOVERY_ROOTS_KEY not in data:
            roots = list(current.roots)
            return roots or [self._resolver.project_root]
        entries = cast(
            Iterable[Path | str],
            _coerce_iterable(data[FILE_DISCOVERY_ROOTS_KEY], "file_discovery.roots"),
        )
        return _unique_paths(self._resolver.resolve_iterable(entries))

    def _merge_excludes(
        self,
        data: Mapping[str, ConfigValue],
        current: FileDiscoveryConfig,
    ) -> list[Path]:
        """Merge path exclusions for the file discovery section.

        Args:
            data: Mapping of raw section values.
            current: Existing file discovery configuration.

        Returns:
            List of resolved excluded paths without duplicates.

        """

        excludes = _unique_paths(current.excludes)
        if FILE_DISCOVERY_EXCLUDES_KEY not in data:
            return excludes
        entries = cast(
            Iterable[Path | str],
            _coerce_iterable(data[FILE_DISCOVERY_EXCLUDES_KEY], "file_discovery.excludes"),
        )
        for resolved in self._resolver.resolve_iterable(entries):
            if resolved not in excludes:
                excludes.append(resolved)
        return excludes

    def _merge_explicit_files(
        self,
        data: Mapping[str, ConfigValue],
        current: FileDiscoveryConfig,
    ) -> list[Path]:
        """Merge explicit file targets for the file discovery section.

        Args:
            data: Mapping of raw section values.
            current: Existing file discovery configuration.

        Returns:
            List of resolved explicit file paths that exist on disk.

        """

        explicit_files = _existing_unique_paths(current.explicit_files)
        if FILE_DISCOVERY_EXPLICIT_KEY not in data:
            return explicit_files
        entries = cast(
            Iterable[Path | str],
            _coerce_iterable(
                data[FILE_DISCOVERY_EXPLICIT_KEY],
                "file_discovery.explicit_files",
            ),
        )
        for resolved in self._resolver.resolve_iterable(entries):
            if resolved.exists() and resolved not in explicit_files:
                explicit_files.append(resolved)
        return explicit_files

    def _merge_limit_to(
        self,
        data: Mapping[str, ConfigValue],
        current: FileDiscoveryConfig,
    ) -> list[Path]:
        """Merge ``limit_to`` paths for the file discovery section.

        Args:
            data: Mapping of raw section values.
            current: Existing file discovery configuration.

        Returns:
            List of resolved paths limiting discovery scope.

        """

        if FILE_DISCOVERY_LIMIT_KEY not in data:
            return _unique_paths(current.limit_to)
        entries = cast(
            Iterable[Path | str],
            _coerce_iterable(data[FILE_DISCOVERY_LIMIT_KEY], "file_discovery.limit_to"),
        )
        return _unique_paths(self._resolver.resolve_iterable(entries))


class _OutputSection(_SectionMerger[OutputConfig]):
    """Merge output configuration sections."""

    section = "output"
    _BOOLEAN_FIELDS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("verbose", "output.verbose"),
        ("emoji", "output.emoji"),
        ("color", "output.color"),
        ("show_passing", "output.show_passing"),
        ("show_stats", "output.show_stats"),
        ("group_by_code", "output.group_by_code"),
        ("report_include_raw", "output.report_include_raw"),
        ("gha_annotations", "output.gha_annotations"),
        ("annotations_use_json", "output.annotations_use_json"),
        ("quiet", "output.quiet"),
        ("advice", "output.advice"),
    )
    _PATH_FIELDS: ClassVar[tuple[tuple[str, str, str], ...]] = (
        (OUTPUT_PR_SUMMARY_OUT_KEY, "pr_summary_out", "output.pr_summary_out"),
        (OUTPUT_REPORT_OUT_KEY, "report_out", "output.report_out"),
        (OUTPUT_SARIF_OUT_KEY, "sarif_out", "output.sarif_out"),
    )

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

        updates: dict[str, ModelUpdateValue] = {}
        updates.update(self._path_updates(data, current))
        updates.update(self._boolean_updates(data, current))
        updates["tool_filters"] = (
            _normalize_tool_filters(data[OUTPUT_TOOL_FILTERS_KEY], current.tool_filters)
            if OUTPUT_TOOL_FILTERS_KEY in data
            else current.tool_filters
        )
        updates["pr_summary_min_severity"] = _normalize_min_severity(
            str(data.get(OUTPUT_MIN_SEVERITY_KEY, current.pr_summary_min_severity)),
        )
        updates["output"] = _normalize_output_mode(str(data.get("output", current.output)))
        updates["pretty_format"] = self._coerce_string(
            data.get("pretty_format", current.pretty_format),
            "output.pretty_format",
        )
        updates["report"] = self._coerce_optional_string(
            data.get("report", current.report),
            "output.report",
        )
        updates["pr_summary_limit"] = _coerce_optional_int(
            data.get("pr_summary_limit"),
            current.pr_summary_limit,
            "output.pr_summary_limit",
        )
        updates["pr_summary_template"] = self._coerce_string(
            data.get("pr_summary_template", current.pr_summary_template),
            "output.pr_summary_template",
        )
        updated = _model_replace(current, updates=updates)
        return updated, self._diff_model(current, updated)

    def _path_updates(
        self,
        data: Mapping[str, ConfigValue],
        current: OutputConfig,
    ) -> dict[str, Path | None]:
        """Collect optional path updates for the output section.

        Args:
            data: Mapping of raw section values.
            current: Existing output configuration model.

        Returns:
            Mapping of output path attributes to their resolved values.

        """

        return {
            attr: self._resolve_optional_path_field(data, key, getattr(current, attr), context)
            for key, attr, context in self._PATH_FIELDS
        }

    def _boolean_updates(
        self,
        data: Mapping[str, ConfigValue],
        current: OutputConfig,
    ) -> dict[str, bool]:
        """Collect optional boolean updates for the output section.

        Args:
            data: Mapping of raw section values.
            current: Existing output configuration model.

        Returns:
            Mapping of boolean output options to their merged values.

        """

        return {
            attr: _coerce_optional_bool(data.get(attr), getattr(current, attr), context)
            for attr, context in self._BOOLEAN_FIELDS
        }

    def _resolve_optional_path_field(
        self,
        data: Mapping[str, ConfigValue],
        key: str,
        current_value: Path | None,
        context: str,
    ) -> Path | None:
        """Resolve optional path configuration values for a given ``key``.

        Args:
            data: Mapping of raw configuration values for the section.
            key: Key within ``data`` to resolve.
            current_value: Existing path value used when ``key`` is absent.
            context: Dot-delimited configuration key for error reporting.

        Returns:
            Optional[Path]: Resolved path value when available.

        """

        raw_value = data.get(key)
        candidate = _ensure_optional_path(
            raw_value if raw_value is not None else current_value,
            context,
        )
        return self._resolver.resolve_optional(candidate)

    @staticmethod
    def _coerce_string(value: ConfigValue, context: str) -> str:
        """Validate that ``value`` is a string.

        Args:
            value: Raw configuration value expected to be a string.
            context: Dot-delimited configuration key for error reporting.

        Returns:
            str: Validated string value.

        Raises:
            ConfigError: If ``value`` is not a string.

        """

        if not isinstance(value, str):
            raise ConfigError(f"{context} must be a string")
        return value

    @staticmethod
    def _coerce_optional_string(value: ConfigValue | None, context: str) -> str | None:
        """Validate that ``value`` is ``None`` or a string.

        Args:
            value: Raw configuration value expected to be optional string.
            context: Dot-delimited configuration key for error reporting.

        Returns:
            Optional[str]: Original value when valid or ``None``.

        Raises:
            ConfigError: If ``value`` is neither ``None`` nor string.

        """

        if value is None or isinstance(value, str):
            return value
        raise ConfigError(f"{context} must be null or a string")


class _ExecutionSection(_SectionMerger[ExecutionConfig]):
    """Merge execution configuration sections."""

    section = "execution"
    _SEQUENCE_FIELDS: ClassVar[tuple[tuple[str, str, str], ...]] = (
        (EXECUTION_ONLY_KEY, "only", "execution.only"),
        (EXECUTION_LANGUAGES_KEY, "languages", "execution.languages"),
        (EXECUTION_ENABLE_KEY, "enable", "execution.enable"),
    )
    _BOOLEAN_FIELDS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("strict", "execution.strict"),
        ("fix_only", "execution.fix_only"),
        ("check_only", "execution.check_only"),
        ("force_all", "execution.force_all"),
        ("respect_config", "execution.respect_config"),
        ("cache_enabled", "execution.cache_enabled"),
        ("use_local_linters", "execution.use_local_linters"),
    )

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

        updates: dict[str, ModelUpdateValue] = {
            attr: self._coerce_sequence_field(data, key, getattr(current, attr), context)
            for key, attr, context in self._SEQUENCE_FIELDS
        }

        updates["cache_dir"] = self._resolve_cache_dir(data.get("cache_dir"), current.cache_dir)

        bail = _coerce_optional_bool(data.get("bail"), current.bail, "execution.bail")
        jobs = _coerce_optional_int(data.get("jobs"), current.jobs, "execution.jobs")
        if bail:
            jobs = 1
        updates["bail"] = bail
        updates["jobs"] = jobs

        for attr, context in self._BOOLEAN_FIELDS:
            updates[attr] = _coerce_optional_bool(data.get(attr), getattr(current, attr), context)

        updated = _model_replace(current, updates=updates)
        return updated, self._diff_model(current, updated)

    def _coerce_sequence_field(
        self,
        data: Mapping[str, ConfigValue],
        key: str,
        current_values: Sequence[str],
        context: str,
    ) -> list[str]:
        """Coerce optional string sequences for execution fields.

        Args:
            data: Mapping containing raw configuration overrides.
            key: Section key that may provide sequence overrides.
            current_values: Existing sequence preserved when ``key`` is absent.
            context: Dot-delimited configuration key for error reporting.

        Returns:
            list[str]: Normalised list of string values.

        """

        if key not in data:
            return list(current_values)
        return _coerce_string_sequence(data[key], context)

    def _resolve_cache_dir(self, raw: ConfigValue | Path | None, current: Path) -> Path:
        """Resolve the execution cache directory value.

        Args:
            raw: Raw configuration value used to override the cache directory.
            current: Existing cache directory path.

        Returns:
            Path: Resolved cache directory path.

        Raises:
            ConfigError: If ``raw`` is neither a path nor a string.

        """

        if raw is None:
            return current
        if not isinstance(raw, (Path, str)):
            raise ConfigError("execution.cache_dir must be a path or string")
        return self._resolver.resolve(raw)


class _LicenseSection(_SectionMerger[LicenseConfig]):
    """Merge license configuration sections."""

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
    """Merge quality configuration sections."""

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
        entries = _coerce_iterable(raw, "quality.schema_targets")
        resolved: list[Path] = []
        for entry in cast(Iterable[Path | str], entries):
            if not isinstance(entry, (str, Path)):
                raise ConfigError("quality.schema_targets entries must be paths")
            resolved.append(self._resolver.resolve(entry))
        return resolved


class _GenericValueTypesSection(_SectionMerger[GenericValueTypesConfig]):
    """Merge generic value-type configuration sections."""

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
            else:
                entries = _coerce_iterable(raw_rules, "generic_value_types.rules")
                rules = tuple(GenericValueTypesRule.model_validate(rule) for rule in entries)

        implications = current.implications
        if GENERIC_VALUE_TYPES_IMPLICATIONS_KEY in data:
            raw_implications = data[GENERIC_VALUE_TYPES_IMPLICATIONS_KEY]
            if raw_implications is None:
                implications = ()
            else:
                entries = _coerce_iterable(raw_implications, "generic_value_types.implications")
                implications = tuple(GenericValueTypesImplication.model_validate(entry) for entry in entries)

        updates: dict[str, ModelUpdateValue] = {
            "enabled": enabled_raw,
            "rules": rules,
            "implications": implications,
        }
        updated = _model_replace(current, updates=updates)
        return updated, self._diff_model(current, updated)


class _CleanSection(_SectionMerger[CleanConfig]):
    """Merge clean configuration sections."""

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
    """Merge update configuration sections."""

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
    """Merge dedupe configuration sections."""

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
    """Construct section mergers keyed by configuration attribute.

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
