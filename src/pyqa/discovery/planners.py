# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Project scanner strategy construction utilities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ..catalog.command_options import OptionMapping, compile_option_mappings
from ..catalog.loader import CatalogIntegrityError
from ..catalog.types import JSONValue
from ..tools.builtin_helpers import _resolve_path, _setting, _settings_list
from ..tools.interfaces import CommandBuilder, ToolContext
from .rules import compile_exclude_arguments, is_under_any

__all__ = ["build_project_scanner"]


_CURRENT_DIRECTORY_MARKER: Final[str] = "."


@dataclass(slots=True)
class _ProjectTargetPlan:
    """Build the configuration for deriving scanner targets."""

    settings: tuple[str, ...]
    include_discovery_roots: bool
    include_discovery_explicit: bool
    fallback_paths: tuple[str, ...]
    default_to_root: bool
    filter_excluded: bool
    prefix: str | None

    def resolve(
        self,
        ctx: ToolContext,
        *,
        files: Sequence[Path],
        excluded: set[Path],
        root: Path,
    ) -> list[str]:
        """Build the project scanner targets from user configuration.

        Args:
            ctx: Tool execution context containing discovery settings.
            files: File selection supplied by the orchestrator.
            excluded: Paths omitted by discovery configuration or command-line
                overrides.
            root: Project root path associated with the current invocation.

        Returns:
            list[str]: CLI arguments identifying the files or directories the
                scanner should analyse.
        """

        file_targets = self._file_targets(files=files, excluded=excluded)
        if file_targets:
            return self._format_targets(file_targets, apply_prefix=False)

        targets = set(self._configured_targets(ctx, excluded=excluded, root=root))
        self._merge_discovery_targets(ctx, targets=targets, excluded=excluded, root=root)

        if not targets:
            targets.update(self._fallback_targets(excluded=excluded, root=root))

        if not targets and self.default_to_root and not self._is_excluded(root, excluded):
            targets.add(root)

        return self._format_targets(targets, apply_prefix=True)

    def _file_targets(self, *, files: Sequence[Path], excluded: set[Path]) -> set[Path]:
        """Build the file-based scanner targets.

        Args:
            files: File selection supplied by the orchestrator.
            excluded: Paths omitted by discovery configuration or command-line
                overrides.

        Returns:
            set[Path]: Resolved, de-duplicated file paths not present in
                ``excluded``.
        """

        candidates: set[Path] = set()
        for file_path in files:
            if self._is_excluded(file_path, excluded):
                continue
            candidates.add(file_path)
        return candidates

    def _configured_targets(
        self,
        ctx: ToolContext,
        *,
        excluded: set[Path],
        root: Path,
    ) -> list[Path]:
        """Build the targets supplied through configuration settings.

        Args:
            ctx: Tool execution context containing configuration overrides.
            excluded: Paths omitted by discovery configuration.
            root: Project root path associated with the current invocation.

        Returns:
            list[Path]: Candidate paths gathered from configuration fields.
        """

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
        """Apply discovery-derived path updates to targets when configured.

        Args:
            ctx: Tool execution context containing file discovery state.
            targets: Mutable target collection to update in place.
            excluded: Paths omitted by discovery configuration.
            root: Project root path associated with the current invocation.
        """

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
        """Return fallback targets when configuration yields no results.

        Args:
            excluded: Paths omitted by discovery configuration.
            root: Project root path associated with the current invocation.

        Returns:
            set[Path]: Candidate fallback directories or files.
        """

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

    def _format_targets(self, targets: set[Path], *, apply_prefix: bool) -> list[str]:
        """Return formatted CLI arguments for targets.

        Args:
            targets: Target collection to render.
            apply_prefix: Flag indicating whether to prepend the configured
                prefix to each entry.

        Returns:
            list[str]: Sorted CLI argument list referencing the supplied
                targets.
        """

        if not targets:
            return []
        formatted: list[str] = []
        prefix = self.prefix if apply_prefix else None
        for path in sorted(targets):
            text = str(path)
            if prefix:
                formatted.extend([prefix, text])
            else:
                formatted.append(text)
        return formatted

    def _is_excluded(self, candidate: Path, excluded: set[Path]) -> bool:
        """Return ``True`` when ``candidate`` should be omitted.

        Args:
            candidate: Path to evaluate against excluded directories.
            excluded: Paths omitted by discovery configuration.

        Returns:
            bool: ``True`` when ``candidate`` resides within ``excluded``.
        """

        if not self.filter_excluded:
            return False
        return is_under_any(candidate, excluded)


@dataclass(slots=True)
class _ProjectScannerStrategy(CommandBuilder):
    """Represent a command builder orchestrating project-aware scanners."""

    base: tuple[str, ...]
    options: tuple[OptionMapping, ...]
    exclude_settings: tuple[str, ...]
    include_discovery_excludes: bool
    exclude_flag: str | None
    exclude_separator: str
    target_plan: _ProjectTargetPlan | None

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Return the scanner command considering excludes and targets.

        Args:
            ctx: Tool execution context used to resolve files and settings.

        Returns:
            Sequence[str]: CLI arguments that should be executed.
        """

        root = ctx.root
        command = list(self.base)
        excluded_paths = self._collect_excluded_paths(ctx, root)
        self._apply_exclude_arguments(command, excluded_paths, root)
        self._apply_option_mappings(ctx, command)
        self._append_targets(ctx, command, excluded_paths, root)
        return tuple(command)

    def _collect_excluded_paths(self, ctx: ToolContext, root: Path) -> set[Path]:
        """Build the set of paths to omit from command targets.

        Args:
            ctx: Tool execution context used to gather settings.
            root: Project root path associated with the current invocation.

        Returns:
            set[Path]: Paths excluded via configuration or discovery.
        """

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
        """Append exclusion arguments to ``command`` when configured.

        Args:
            command: Argument sequence under construction.
            excluded_paths: Paths that should be omitted from command targets.
            root: Project root path associated with the current invocation.
        """

        if not self.exclude_flag or not excluded_paths:
            return
        exclude_args = compile_exclude_arguments(excluded_paths, root)
        if not exclude_args:
            return
        joined = self.exclude_separator.join(sorted(exclude_args))
        command.extend([self.exclude_flag, joined])

    def _apply_option_mappings(self, ctx: ToolContext, command: list[str]) -> None:
        """Apply declarative option mappings to ``command``.

        Args:
            ctx: Tool execution context containing settings.
            command: Mutable argument list that will be executed.
        """

        for mapping in self.options:
            mapping.apply(ctx=ctx, command=command)

    def _append_targets(
        self,
        ctx: ToolContext,
        command: list[str],
        excluded_paths: set[Path],
        root: Path,
    ) -> None:
        """Append resolved targets to ``command`` when available.

        Args:
            ctx: Tool execution context providing discovery state.
            command: Mutable argument list that will be executed.
            excluded_paths: Paths to omit from target selection.
            root: Project root path associated with the current invocation.
        """

        if self.target_plan is None:
            return
        targets = self.target_plan.resolve(
            ctx,
            files=ctx.files,
            excluded=excluded_paths,
            root=root,
        )
        if not targets:
            return
        command.extend(targets)


def build_project_scanner(plain_config: Mapping[str, JSONValue]) -> CommandBuilder:
    """Return a project-aware scanner command builder derived from catalog data.

    Args:
        plain_config: Raw configuration payload describing how to assemble the
            scanner command.

    Returns:
        CommandBuilder: Command builder that materialises the configured
            scanner invocation.
    """

    base_config = plain_config.get("base")
    if not isinstance(base_config, Sequence) or isinstance(base_config, (str, bytes, bytearray)):
        raise CatalogIntegrityError("command_project_scanner: 'base' must be an array of arguments")
    base_args = tuple(str(part) for part in base_config)
    if not base_args:
        raise CatalogIntegrityError(
            "command_project_scanner: 'base' must contain at least one argument",
        )

    raw_options = plain_config.get("options")
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
    exclude_settings: tuple[str, ...]
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
    target_plan: _ProjectTargetPlan | None = None
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


def _parse_project_target_plan(entry: JSONValue) -> _ProjectTargetPlan:
    """Return target planning configuration derived from catalog data.

    Args:
        entry: Raw catalog payload describing target discovery behaviour.

    Returns:
        _ProjectTargetPlan: Normalised plan ready for runtime evaluation.

    Raises:
        CatalogIntegrityError: If ``entry`` does not conform to the expected schema.
    """

    if not isinstance(entry, Mapping):
        raise CatalogIntegrityError("command_project_scanner.targets must be an object")

    settings_value = entry.get("settings", ())
    settings: tuple[str, ...]
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
    fallback_paths: tuple[str, ...]
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
        prefix: str | None = None
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
