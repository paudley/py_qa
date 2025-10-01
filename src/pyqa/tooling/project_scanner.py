# SPDX-License-Identifier: MIT
"""Project scanner strategy construction utilities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, cast

from ..tools.base import CommandBuilder, ToolContext
from ..tools.builtin_helpers import _resolve_path, _setting, _settings_list
from .catalog.types import JSONValue
from .command_options import OptionMapping, compile_option_mappings
from .loader import CatalogIntegrityError

__all__ = ["build_project_scanner"]


_CURRENT_DIRECTORY_MARKER: Final[str] = "."
_PATH_SEPARATOR: Final[str] = "/"


@dataclass(slots=True)
class _ProjectTargetPlan:
    """Configuration for deriving scanner targets."""

    settings: tuple[str, ...]
    include_discovery_roots: bool
    include_discovery_explicit: bool
    fallback_paths: tuple[str, ...]
    default_to_root: bool
    filter_excluded: bool
    prefix: str | None

    def resolve(self, ctx: ToolContext, *, excluded: set[Path], root: Path) -> list[str]:
        """Return project scanner targets derived from user configuration."""

        targets = set(self._configured_targets(ctx, excluded=excluded, root=root))
        self._merge_discovery_targets(ctx, targets=targets, excluded=excluded, root=root)

        if not targets:
            targets.update(self._fallback_targets(excluded=excluded, root=root))

        if not targets and self.default_to_root and not self._is_excluded(root, excluded):
            targets.add(root)

        return self._format_targets(targets)

    def _configured_targets(
        self,
        ctx: ToolContext,
        *,
        excluded: set[Path],
        root: Path,
    ) -> list[Path]:
        """Return targets configured via explicit settings."""

        results: list[Path] = []
        for name in self.settings:
            for value in _settings_list(_setting(ctx.settings, name)):
                candidate = _resolve_path(root, value)
                if self._is_excluded(candidate, excluded):
                    continue
                results.append(candidate)
        return results

    def _merge_discovery_targets(
        self,
        ctx: ToolContext,
        *,
        targets: set[Path],
        excluded: set[Path],
        root: Path,
    ) -> None:
        """Add discovery-derived directories to ``targets`` when enabled."""

        discovery = getattr(ctx.cfg, "file_discovery", None)
        if discovery is None:
            return

        if self.include_discovery_roots:
            for directory in discovery.roots:
                resolved = directory if directory.is_absolute() else root / directory
                if resolved == root or self._is_excluded(resolved, excluded):
                    continue
                targets.add(resolved)

        if self.include_discovery_explicit:
            for file_path in discovery.explicit_files:
                resolved_file = file_path if file_path.is_absolute() else root / file_path
                parent = resolved_file.parent
                if self._is_excluded(parent, excluded):
                    continue
                targets.add(parent)

    def _fallback_targets(self, *, excluded: set[Path], root: Path) -> set[Path]:
        """Return fallback targets when no configured targets exist."""

        candidates: set[Path] = set()
        for fallback in self.fallback_paths:
            candidate = _resolve_path(root, fallback)
            if fallback != _CURRENT_DIRECTORY_MARKER and not candidate.exists():
                continue
            if self._is_excluded(candidate, excluded):
                continue
            candidates.add(candidate)
            break
        return candidates

    def _format_targets(self, targets: set[Path]) -> list[str]:
        """Return sorted string representations applying optional prefix."""

        if not targets:
            return []
        formatted: list[str] = []
        for path in targets:
            text = str(path)
            if self.prefix:
                text = f"{self.prefix}{text}"
            formatted.append(text)
        return sorted(set(formatted))

    def _is_excluded(self, candidate: Path, excluded: set[Path]) -> bool:
        """Return ``True`` when ``candidate`` should be omitted."""

        if not self.filter_excluded:
            return False
        return _is_under_any(candidate, excluded)


@dataclass(slots=True)
class _ProjectScannerStrategy(CommandBuilder):
    """Command builder orchestrating project-aware scanners."""

    base: tuple[str, ...]
    options: tuple[OptionMapping, ...]
    exclude_settings: tuple[str, ...]
    include_discovery_excludes: bool
    exclude_flag: str | None
    exclude_separator: str
    target_plan: _ProjectTargetPlan | None

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Compose the scanner command considering excludes and targets."""

        root = ctx.root
        command = list(self.base)
        excluded_paths = self._collect_excluded_paths(ctx, root)
        self._apply_exclude_arguments(command, excluded_paths, root)
        self._apply_option_mappings(ctx, command)
        self._append_targets(ctx, command, excluded_paths, root)
        return tuple(command)

    def _collect_excluded_paths(self, ctx: ToolContext, root: Path) -> set[Path]:
        """Return a set of paths that should be omitted from command targets."""

        excluded: set[Path] = set()
        for name in self.exclude_settings:
            for value in _settings_list(_setting(ctx.settings, name)):
                excluded.add(_resolve_path(root, value))

        if not self.include_discovery_excludes:
            return excluded

        discovery = getattr(ctx.cfg, "file_discovery", None)
        if discovery is None:
            return excluded

        for path in discovery.excludes:
            resolved = path if path.is_absolute() else root / path
            excluded.add(resolved)
        return excluded

    def _apply_exclude_arguments(
        self,
        command: list[str],
        excluded_paths: set[Path],
        root: Path,
    ) -> None:
        """Append exclusion arguments to ``command`` when configured."""

        if not self.exclude_flag or not excluded_paths:
            return
        exclude_args = _compile_exclude_arguments(excluded_paths, root)
        if not exclude_args:
            return
        joined = self.exclude_separator.join(sorted(exclude_args))
        command.extend([self.exclude_flag, joined])

    def _apply_option_mappings(self, ctx: ToolContext, command: list[str]) -> None:
        """Apply declarative option mappings to ``command``."""

        for mapping in self.options:
            mapping.apply(ctx=ctx, command=command)

    def _append_targets(
        self,
        ctx: ToolContext,
        command: list[str],
        excluded_paths: set[Path],
        root: Path,
    ) -> None:
        """Append resolved targets to ``command`` when available."""

        if self.target_plan is None:
            return
        targets = self.target_plan.resolve(ctx, excluded=excluded_paths, root=root)
        if not targets:
            return
        if self.target_plan.prefix:
            command.append(self.target_plan.prefix)
        command.extend(targets)


def build_project_scanner(plain_config: Mapping[str, Any]) -> CommandBuilder:
    """Return a project-aware scanner command builder driven by catalog data."""

    base_config = plain_config.get("base")
    if not isinstance(base_config, Sequence) or isinstance(base_config, (str, bytes, bytearray)):
        raise CatalogIntegrityError("command_project_scanner: 'base' must be an array of arguments")
    base_args = tuple(str(part) for part in base_config)
    if not base_args:
        raise CatalogIntegrityError(
            "command_project_scanner: 'base' must contain at least one argument",
        )

    raw_options = cast(JSONValue | None, plain_config.get("options"))
    option_mappings = compile_option_mappings(
        raw_options,
        context="command_project_scanner.options",
    )

    exclude_config = plain_config.get("exclude", {})
    if not isinstance(exclude_config, Mapping):
        raise CatalogIntegrityError(
            "command_project_scanner: 'exclude' must be an object when provided",
        )
    exclude_settings_value = exclude_config.get("settings", ())
    if isinstance(exclude_settings_value, str):
        exclude_settings = (exclude_settings_value,)
    elif isinstance(exclude_settings_value, Sequence) and not isinstance(
        exclude_settings_value,
        (str, bytes, bytearray),
    ):
        exclude_settings = tuple(str(item) for item in exclude_settings_value if item is not None)
    else:
        raise CatalogIntegrityError(
            "command_project_scanner: exclude.settings must be string or array of strings",
        )

    include_discovery_excludes = bool(exclude_config.get("includeDiscovery", False))
    exclude_flag_value = exclude_config.get("flag")
    if exclude_flag_value is None:
        exclude_flag = None
    elif isinstance(exclude_flag_value, str):
        exclude_flag = exclude_flag_value
    else:
        raise CatalogIntegrityError(
            "command_project_scanner: exclude.flag must be a string when provided",
        )

    separator_value = exclude_config.get("separator", ",")
    if not isinstance(separator_value, str) or not separator_value:
        raise CatalogIntegrityError(
            "command_project_scanner: exclude.separator must be a non-empty string",
        )

    targets_config = plain_config.get("targets")
    target_plan = None
    if targets_config is not None:
        target_plan = _parse_project_target_plan(targets_config)

    return _ProjectScannerStrategy(
        base=base_args,
        options=option_mappings,
        exclude_settings=exclude_settings,
        include_discovery_excludes=include_discovery_excludes,
        exclude_flag=exclude_flag,
        exclude_separator=separator_value,
        target_plan=target_plan,
    )


def _parse_project_target_plan(entry: Any) -> _ProjectTargetPlan:
    """Materialise target planning configuration from catalog data."""

    if not isinstance(entry, Mapping):
        raise CatalogIntegrityError("command_project_scanner.targets must be an object")

    settings_value = entry.get("settings", ())
    if isinstance(settings_value, str):
        settings = (settings_value,)
    elif isinstance(settings_value, Sequence) and not isinstance(
        settings_value,
        (str, bytes, bytearray),
    ):
        settings = tuple(str(item) for item in settings_value if item is not None)
    else:
        raise CatalogIntegrityError(
            "command_project_scanner.targets.settings must be string or array of strings",
        )

    include_roots = bool(entry.get("includeDiscoveryRoots", False))
    include_explicit = bool(entry.get("includeDiscoveryExplicit", False))

    fallback_value = entry.get("fallback", ())
    if isinstance(fallback_value, str):
        fallback_paths = (fallback_value,)
    elif isinstance(fallback_value, Sequence) and not isinstance(
        fallback_value,
        (str, bytes, bytearray),
    ):
        fallback_paths = tuple(str(item) for item in fallback_value if item is not None)
    else:
        raise CatalogIntegrityError(
            "command_project_scanner.targets.fallback must be string or array of strings",
        )

    default_to_root = bool(entry.get("defaultToRoot", False))
    filter_excluded = bool(entry.get("filterExcluded", True))

    prefix_value = entry.get("prefix")
    if prefix_value is None:
        prefix = None
    elif isinstance(prefix_value, str):
        prefix = prefix_value
    else:
        raise CatalogIntegrityError(
            "command_project_scanner.targets.prefix must be a string when provided",
        )

    return _ProjectTargetPlan(
        settings=settings,
        include_discovery_roots=include_roots,
        include_discovery_explicit=include_explicit,
        fallback_paths=fallback_paths,
        default_to_root=default_to_root,
        filter_excluded=filter_excluded,
        prefix=prefix,
    )


@lru_cache(maxsize=512)
def _normalise_path_requirement(raw: str) -> tuple[str, ...]:
    """Convert requirement string into normalised path segments."""

    cleaned = raw.replace("\\", "/").strip()
    if not cleaned:
        return ()
    segments = [segment for segment in cleaned.split("/") if segment]
    return tuple(segments)


def _path_matches_requirements(
    candidate: Path,
    root: Path,
    requirements: tuple[tuple[str, ...], ...],
) -> bool:
    """Return True when *candidate* satisfies all required path fragments."""

    if not requirements:
        return True

    parts = _candidate_parts(candidate, root)
    if not parts:
        return False

    return all(_has_path_sequence(parts, requirement) for requirement in requirements)


@lru_cache(maxsize=1024)
def _candidate_parts(candidate: Path, root: Path) -> tuple[str, ...]:
    """Return normalised path components for *candidate* relative to *root*.

    Args:
        candidate: Filesystem path produced by catalog configuration.
        root: Root directory associated with the current tool execution.

    Returns:
        tuple[str, ...]: Normalised path parts or an empty tuple when the input
        cannot be resolved.
    """

    relative_path = _resolve_relative_path(candidate, root)
    normalised = _normalise_parts(relative_path)
    if normalised:
        return normalised
    return _fallback_parts(candidate)


def _resolve_relative_path(candidate: Path, root: Path) -> Path | None:
    """Return *candidate* relative to *root* when possible.

    Args:
        candidate: Path to evaluate.
        root: Base path used for relative resolution.

    Returns:
        Path | None: Relative path or ``None`` when resolution fails.
    """

    if not candidate.is_absolute():
        return candidate
    try:
        return candidate.relative_to(root)
    except ValueError:
        return candidate
    except OSError:
        return None


def _normalise_parts(path: Path | None) -> tuple[str, ...]:
    """Return cleaned components for *path* or an empty tuple.

    Args:
        path: Path object to normalise.

    Returns:
        tuple[str, ...]: Tuple of non-empty, non-dot path segments.
    """

    if path is None:
        return ()
    try:
        return tuple(part for part in path.parts if part not in ("", _CURRENT_DIRECTORY_MARKER))
    except OSError:
        return ()


def _fallback_parts(candidate: Path) -> tuple[str, ...]:
    """Return path components using POSIX splitting when direct methods fail.

    Args:
        candidate: Path to split.

    Returns:
        tuple[str, ...]: Fallback sequence of path segments.
    """

    return tuple(segment for segment in candidate.as_posix().split(_PATH_SEPARATOR) if segment)


def _has_path_sequence(parts: Sequence[str], required: tuple[str, ...]) -> bool:
    """Check whether *required* appears as a contiguous sequence within *parts*."""

    if not required:
        return True
    if len(required) == 1:
        target = required[0]
        return any(part == target for part in parts)

    length = len(required)
    limit = len(parts) - length + 1
    if limit <= 0:
        return False
    return any(tuple(parts[offset : offset + length]) == required for offset in range(limit))


def _compile_exclude_arguments(excluded_paths: set[Path], root: Path) -> set[str]:
    """Build CLI exclusion arguments for discovery-aware scanners."""

    arguments: set[str] = set()
    resolved_root = root.resolve()
    for path in excluded_paths:
        resolved = path.resolve()
        arguments.add(str(resolved))
        relative = _relative_to_root(resolved, resolved_root)
        if relative is not None:
            arguments.add(relative)
    return arguments


def _is_under_any(candidate: Path, bases: set[Path]) -> bool:
    """Return ``True`` if ``candidate`` resides within any path in ``bases``."""

    return any(_is_under_base(candidate, base) for base in bases)


def _relative_to_root(path: Path, root: Path) -> str | None:
    """Return the relative string representation of *path* to *root*.

    Args:
        path: Absolute path to relativise.
        root: Root directory used for relativisation.

    Returns:
        str | None: Relative path string or ``None`` when *path* lies outside
        of *root*.
    """

    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    return str(relative)


def _is_under_base(candidate: Path, base: Path) -> bool:
    """Return ``True`` if ``candidate`` resides within ``base``.

    Args:
        candidate: Path being evaluated for containment.
        base: Directory that may contain ``candidate``.

    Returns:
        bool: ``True`` when ``candidate`` is within ``base``.
    """

    try:
        candidate.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True
