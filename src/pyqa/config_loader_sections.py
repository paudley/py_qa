# SPDX-License-Identifier: MIT
"""Section-specific configuration merge helpers for :mod:`pyqa.config_loader`."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Generic, TypeVar, cast

from pydantic import BaseModel, ConfigDict, model_validator

from .config import (
    CleanConfig,
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
    _existing_unique_paths,
    _normalize_min_severity,
    _normalize_output_mode,
    _normalize_tool_filters,
    _unique_paths,
)

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


class PathResolver(BaseModel):
    """Convert path-like values relative to the project root."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_root: Path

    @model_validator(mode="after")
    def _normalise_root(self) -> PathResolver:
        object.__setattr__(self, "project_root", self.project_root.resolve())
        return self

    def resolve(self, value: Path | str) -> Path:
        """Return an absolute path for ``value`` relative to the project root."""

        candidate = value if isinstance(value, Path) else Path(value)
        candidate = candidate.expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.project_root / candidate).resolve()

    def resolve_optional(self, value: Path | str | None) -> Path | None:
        """Resolve ``value`` while preserving ``None`` inputs."""

        if value is None:
            return None
        return self.resolve(value)

    def resolve_iterable(self, values: Iterable[Path | str]) -> list[Path]:
        """Resolve a collection of path-like values."""

        return [self.resolve(value) for value in values]


def _model_replace(instance: ModelT, **updates: Any) -> ModelT:
    """Return a defensive deep copy of ``instance`` with ``updates`` applied."""

    if not isinstance(instance, BaseModel):  # defensive guard for legacy usage
        raise TypeError("_model_replace expects a Pydantic BaseModel instance")
    return cast("ModelT", instance.model_copy(update=updates, deep=True))


def _coerce_optional_str_value(value: Any, current: str | None, context: str) -> str | None:
    """Return cleaned string values allowing ``None`` defaults."""

    if value is None:
        return current
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    raise ConfigError(f"{context} must be a string")


def _coerce_optional_bool(value: Any, current: bool, context: str) -> bool:
    """Return cleaned bool values allowing ``None`` defaults."""

    if value is None:
        return current
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{context} must be a boolean")


class _SectionMerger(Generic[ModelT], ABC):
    """Base utilities for section-specific merge implementations."""

    section: SectionName

    def describe_section(self) -> SectionName:
        """Return the section identifier managed by this merger."""

        return self.section

    @abstractmethod
    def merge(self, current: ModelT, raw: Any) -> tuple[ModelT, dict[str, Any]]:
        """Return updated section model merged with raw configuration data."""

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


class _FileDiscoverySection(_SectionMerger[FileDiscoveryConfig]):
    section = "file_discovery"

    def __init__(self, resolver: PathResolver) -> None:
        self._resolver = resolver

    def merge(
        self,
        current: FileDiscoveryConfig,
        raw: Any,
    ) -> tuple[FileDiscoveryConfig, dict[str, Any]]:
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
            pre_commit=data.get("pre_commit", current.pre_commit),
            respect_gitignore=data.get("respect_gitignore", current.respect_gitignore),
            limit_to=limit_to,
        )
        return updated, self._diff_model(current, updated)


class _OutputSection(_SectionMerger[OutputConfig]):
    section = "output"

    def __init__(self, resolver: PathResolver) -> None:
        self._resolver = resolver

    def merge(self, current: OutputConfig, raw: Any) -> tuple[OutputConfig, dict[str, Any]]:
        data = self._ensure_mapping(raw, self.section)

        tool_filters = current.tool_filters
        if OUTPUT_TOOL_FILTERS_KEY in data:
            tool_filters = _normalize_tool_filters(
                data[OUTPUT_TOOL_FILTERS_KEY],
                current.tool_filters,
            )

        pr_summary_min = data.get(OUTPUT_MIN_SEVERITY_KEY, current.pr_summary_min_severity)
        pr_summary_min_severity = _normalize_min_severity(pr_summary_min)

        pr_summary_out = self._resolver.resolve_optional(
            data.get(OUTPUT_PR_SUMMARY_OUT_KEY, current.pr_summary_out),
        )
        report_out = self._resolver.resolve_optional(data.get(OUTPUT_REPORT_OUT_KEY, current.report_out))
        sarif_out = self._resolver.resolve_optional(data.get(OUTPUT_SARIF_OUT_KEY, current.sarif_out))

        output_mode = _normalize_output_mode(data.get("output", current.output))

        updated = _model_replace(
            current,
            verbose=data.get("verbose", current.verbose),
            emoji=data.get("emoji", current.emoji),
            color=data.get("color", current.color),
            show_passing=data.get("show_passing", current.show_passing),
            show_stats=data.get("show_stats", current.show_stats),
            output=output_mode,
            pretty_format=data.get("pretty_format", current.pretty_format),
            group_by_code=data.get("group_by_code", current.group_by_code),
            report=data.get("report", current.report),
            report_out=report_out,
            report_include_raw=data.get("report_include_raw", current.report_include_raw),
            sarif_out=sarif_out,
            pr_summary_out=pr_summary_out,
            pr_summary_limit=data.get("pr_summary_limit", current.pr_summary_limit),
            pr_summary_min_severity=pr_summary_min_severity,
            pr_summary_template=data.get("pr_summary_template", current.pr_summary_template),
            gha_annotations=data.get("gha_annotations", current.gha_annotations),
            annotations_use_json=data.get("annotations_use_json", current.annotations_use_json),
            quiet=data.get("quiet", current.quiet),
            tool_filters=tool_filters,
            advice=data.get("advice", current.advice),
        )

        if updated.show_passing and updated.quiet:
            updated = _model_replace(updated, show_passing=False)

        return updated, self._diff_model(current, updated)


class _ExecutionSection(_SectionMerger[ExecutionConfig]):
    section = "execution"

    def __init__(self, resolver: PathResolver) -> None:
        self._resolver = resolver

    def merge(self, current: ExecutionConfig, raw: Any) -> tuple[ExecutionConfig, dict[str, Any]]:
        data = self._ensure_mapping(raw, self.section)
        cache_dir_value = data.get("cache_dir", current.cache_dir)
        cache_dir = self._resolver.resolve(cache_dir_value) if cache_dir_value is not None else current.cache_dir

        jobs = data.get("jobs", current.jobs)
        bail = data.get("bail", current.bail)
        if bail:
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


class _LicenseSection(_SectionMerger[LicenseConfig]):
    section = "license"

    def merge(self, current: LicenseConfig, raw: Any) -> tuple[LicenseConfig, dict[str, Any]]:
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


class _QualitySection(_SectionMerger[QualityConfigSection]):
    section = "quality"

    def __init__(self, resolver: PathResolver) -> None:
        self._resolver = resolver

    def merge(
        self,
        current: QualityConfigSection,
        raw: Any,
    ) -> tuple[QualityConfigSection, dict[str, Any]]:
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


class _CleanSection(_SectionMerger[CleanConfig]):
    section = "clean"

    def merge(self, current: CleanConfig, raw: Any) -> tuple[CleanConfig, dict[str, Any]]:
        data = self._ensure_mapping(raw, self.section)

        patterns = list(current.patterns)
        if CLEAN_PATTERNS_KEY in data:
            patterns = _coerce_string_sequence(data[CLEAN_PATTERNS_KEY], "clean.patterns")

        trees = list(current.trees)
        if CLEAN_TREES_KEY in data:
            trees = _coerce_string_sequence(data[CLEAN_TREES_KEY], "clean.trees")

        updated = _model_replace(current, patterns=patterns, trees=trees)
        return updated, self._diff_model(current, updated)


class _UpdateSection(_SectionMerger[UpdateConfig]):
    section = "update"

    def merge(self, current: UpdateConfig, raw: Any) -> tuple[UpdateConfig, dict[str, Any]]:
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


class _DedupeSection(_SectionMerger[DedupeConfig]):
    section = "dedupe"

    def merge(self, current: DedupeConfig, raw: Any) -> tuple[DedupeConfig, dict[str, Any]]:
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


def build_section_mergers(resolver: PathResolver) -> tuple[tuple[str, _SectionMerger[Any]], ...]:
    """Return configured section mergers keyed by configuration attribute."""

    return (
        ("file_discovery", _FileDiscoverySection(resolver)),
        ("output", _OutputSection(resolver)),
        ("execution", _ExecutionSection(resolver)),
        ("dedupe", _DedupeSection()),
        ("license", _LicenseSection()),
        ("quality", _QualitySection(resolver)),
        ("clean", _CleanSection()),
        ("update", _UpdateSection()),
    )


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
    "UPDATE_ENABLED_MANAGERS_KEY",
    "UPDATE_SKIP_PATTERNS_KEY",
    "_SectionMerger",
    "_coerce_optional_bool",
    "_coerce_optional_str_value",
    "_model_replace",
    "build_section_mergers",
]
