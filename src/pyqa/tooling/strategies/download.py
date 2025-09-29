"""Download-backed command strategies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from ..loader import CatalogIntegrityError
from ..tools.base import CommandBuilder, ToolContext
from ..tools.builtin_helpers import _as_bool, _resolve_path, _setting, _settings_list
from .common import (
    _as_plain_json,
    _download_artifact_for_tool,
)
from ..catalog.types import JSONValue

DEFAULT_BINARY_PLACEHOLDER = "${binary}"


@dataclass(slots=True)
class _CommandOption:
    """Declarative mapping between tool settings and CLI arguments."""

    primary: str
    aliases: tuple[str, ...]
    kind: Literal["value", "path", "args", "flag", "repeatFlag"]
    flag: str | None
    join_separator: str | None
    negate_flag: str | None
    literal_values: tuple[str, ...]
    default: JSONValue | None

    def apply(self, *, ctx: ToolContext, command: list[str]) -> None:
        """Append CLI arguments derived from the configured option.

        Args:
            ctx: Tool execution context containing user settings.
            command: Mutable command list to augment with option-derived values.
        """

        raw_value = cast(JSONValue | None, _setting(ctx.settings, self.primary, *self.aliases))
        if raw_value is None and self.default is not None:
            raw_value = self.default
        if raw_value is None:
            return
        if self.kind == "args":
            values = _settings_list(raw_value)
            if not values:
                return
            if self.join_separator is not None:
                combined = self.join_separator.join(str(item) for item in values)
                if self.flag:
                    command.extend([self.flag, combined])
                else:
                    command.append(combined)
                return
            for entry in values:
                if self.flag:
                    command.extend([self.flag, str(entry)])
                else:
                    command.append(str(entry))
            return
        if self.kind == "path":
            if isinstance(raw_value, (str, Path)) and str(raw_value) in self.literal_values:
                value = str(raw_value)
            else:
                value = str(_resolve_path(ctx.root, raw_value))
            if self.flag:
                command.extend([self.flag, value])
            else:
                command.append(value)
            return
        if self.kind == "value":
            value = str(raw_value)
            if self.flag:
                command.extend([self.flag, value])
            else:
                command.append(value)
            return
        if self.kind == "flag":
            bool_value = _as_bool(raw_value)
            if bool_value is None:
                return
            if bool_value:
                if self.flag:
                    command.append(self.flag)
            elif self.negate_flag:
                command.append(self.negate_flag)
            return
        if self.kind == "repeatFlag":
            if self.flag is None:
                return
            count: int
            if isinstance(raw_value, bool):
                count = 1 if raw_value else 0
            elif isinstance(raw_value, (int, float)):
                count = max(int(raw_value), 0)
            else:
                try:
                    count = max(int(str(raw_value)), 0)
                except (TypeError, ValueError):
                    count = 0
            if count == 0:
                if self.negate_flag:
                    command.append(self.negate_flag)
                return
            command.extend([self.flag] * count)
            return
        raise CatalogIntegrityError("command option encountered unsupported type")


@dataclass(slots=True)
class _TargetSelector:
    """Derive command targets from file discovery metadata."""

    mode: Literal["filePattern"]
    suffixes: tuple[str, ...]
    contains: tuple[str, ...]
    fallback_directory: str | None
    default_to_root: bool

    def select(self, ctx: ToolContext, *, excluded: set[Path]) -> list[str]:
        """Return target arguments resolved from the tool context."""

        matched: list[Path] = []
        for path in ctx.files:
            if not isinstance(path, Path):
                candidate = Path(str(path))
            else:
                candidate = path
            text = str(candidate)
            if self.suffixes and not text.endswith(self.suffixes):
                continue
            if self.contains and not any(fragment in text for fragment in self.contains):
                continue
            matched.append(candidate)

        if matched:
            return [str(path) for path in matched]

        root = ctx.root
        if self.fallback_directory:
            fallback_path = _resolve_path(root, self.fallback_directory)
            if fallback_path.exists() and not _is_under_any(fallback_path, excluded):
                return [str(fallback_path)]

        if self.default_to_root:
            return [str(root)]
        return []


@dataclass(slots=True)
class _DownloadBinaryStrategy(CommandBuilder):
    """Command builder that executes downloaded binaries with mapped options."""

    version: str | None
    download: Mapping[str, JSONValue]
    base: tuple[str, ...]
    placeholder: str
    options: tuple[_CommandOption, ...]
    target_selector: _TargetSelector | None

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Compose the command line for the configured binary.

        Args:
            ctx: Tool execution context containing repository metadata and settings.

        Returns:
            Sequence[str]: Fully rendered command arguments.
        """

        cache_root = ctx.root / ".lint-cache"
        binary = _download_artifact_for_tool(
            self.download,
            version=self.version,
            cache_root=cache_root,
            context="command_download_binary.download",
        )
        command = [str(binary) if part == self.placeholder else str(part) for part in self.base]
        for option in self.options:
            option.apply(ctx=ctx, command=command)
        if self.target_selector is not None:
            targets = self.target_selector.select(ctx, excluded=set())
            if targets:
                command.extend(targets)
        return tuple(command)


def command_download_binary(config: Mapping[str, JSONValue]) -> CommandBuilder:
    """Build a download-backed command strategy.

    Args:
        config: Catalog-driven configuration describing download metadata,
            command arguments, and option mappings.

    Returns:
        CommandBuilder: Strategy instance capable of building the executable
        command for the catalog-defined tool action.

    Raises:
        CatalogIntegrityError: If the configuration is missing required fields or
            contains invalid values.
    """

    plain_config = cast(JSONValue, _as_plain_json(config))
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError("command_download_binary: configuration must be an object")

    download_config = plain_config.get("download")
    if not isinstance(download_config, Mapping):
        raise CatalogIntegrityError("command_download_binary: 'download' must be an object")
    download_mapping = cast(Mapping[str, JSONValue], download_config)

    version_value = plain_config.get("version")
    if version_value is not None and not isinstance(version_value, str):
        raise CatalogIntegrityError("command_download_binary: 'version' must be a string when provided")

    placeholder_value = plain_config.get("binaryPlaceholder")
    if placeholder_value is None:
        placeholder = DEFAULT_BINARY_PLACEHOLDER
    elif isinstance(placeholder_value, str) and placeholder_value.strip():
        placeholder = placeholder_value
    else:
        raise CatalogIntegrityError("command_download_binary: 'binaryPlaceholder' must be a non-empty string")

    base_config = plain_config.get("base")
    if base_config is None:
        base_parts: tuple[str, ...] = (placeholder,)
    elif isinstance(base_config, Sequence) and not isinstance(base_config, (str, bytes, bytearray)):
        extracted = [str(part) for part in base_config if part is not None]
        base_parts = tuple(extracted) if extracted else (placeholder,)
    else:
        raise CatalogIntegrityError("command_download_binary: 'base' must be an array of arguments")
    if placeholder not in base_parts:
        base_parts = (placeholder,) + base_parts

    options_config = plain_config.get("options")
    option_specs: list[_CommandOption] = []
    if options_config is not None:
        if not isinstance(options_config, Sequence) or isinstance(options_config, (str, bytes, bytearray)):
            raise CatalogIntegrityError("command_download_binary: 'options' must be an array of objects")
        for index, entry in enumerate(options_config):
            option_specs.append(_parse_command_option(entry, index=index))

    target_selector_config = plain_config.get("targets")
    target_selector = None
    if target_selector_config is not None:
        target_selector = _parse_target_selector(target_selector_config, context="command_download_binary.targets")

    return _DownloadBinaryStrategy(
        version=version_value,
        download=download_mapping,
        base=base_parts,
        placeholder=placeholder,
        options=tuple(option_specs),
        target_selector=target_selector,
    )


def _parse_command_option(entry: JSONValue, *, index: int) -> _CommandOption:
    """Materialise a command option from catalog configuration.

    Args:
        entry: Raw JSON entry describing the option.
        index: Index of the option within the configuration array, used for
            detailed error messaging.

    Returns:
        _CommandOption: Parsed option ready for application during command
        composition.

    Raises:
        CatalogIntegrityError: If the option definition is malformed.
    """

    context = f"command_download_binary.options[{index}]"
    if not isinstance(entry, Mapping):
        raise CatalogIntegrityError(f"{context}: option must be an object")

    setting_value = entry.get("setting")
    if isinstance(setting_value, str):
        names = (setting_value,)
    elif isinstance(setting_value, Sequence) and not isinstance(setting_value, (str, bytes, bytearray)):
        names = tuple(str(name) for name in setting_value if name is not None)
    else:
        raise CatalogIntegrityError(f"{context}: 'setting' must be a string or array of strings")
    if not names:
        raise CatalogIntegrityError(f"{context}: 'setting' must provide at least one entry")

    type_value = entry.get("type", "value")
    if not isinstance(type_value, str):
        raise CatalogIntegrityError(f"{context}: 'type' must be a string")
    normalized_type_key = type_value.strip().lower()
    type_mapping: dict[str, Literal["value", "path", "args", "flag", "repeatFlag"]] = {
        "value": "value",
        "path": "path",
        "args": "args",
        "flag": "flag",
        "repeatflag": "repeatFlag",
    }
    normalized_type = type_mapping.get(normalized_type_key)
    if normalized_type is None:
        raise CatalogIntegrityError(f"{context}: unsupported option type '{type_value}'")

    flag_value = entry.get("flag")
    if flag_value is not None and not isinstance(flag_value, str):
        raise CatalogIntegrityError(f"{context}: 'flag' must be a string when provided")
    join_value = entry.get("joinWith")
    if join_value is None:
        join_separator = None
    elif isinstance(join_value, str):
        join_separator = join_value
    else:
        raise CatalogIntegrityError(f"{context}: 'joinWith' must be a string when provided")

    negate_flag_value = entry.get("negateFlag")
    if negate_flag_value is None:
        negate_flag = None
    elif isinstance(negate_flag_value, str):
        negate_flag = negate_flag_value
    else:
        raise CatalogIntegrityError(f"{context}: 'negateFlag' must be a string when provided")

    literal_values_value = entry.get("literalValues", ())
    if isinstance(literal_values_value, str):
        literal_values = (literal_values_value,)
    elif isinstance(literal_values_value, Sequence) and not isinstance(literal_values_value, (str, bytes, bytearray)):
        literal_values = tuple(str(item) for item in literal_values_value if item is not None)
    else:
        raise CatalogIntegrityError(f"{context}: 'literalValues' must be a string or array of strings")

    default_value = entry.get("default")

    return _CommandOption(
        primary=names[0],
        aliases=tuple(names[1:]),
        kind=cast(Literal["value", "path", "args", "flag", "repeatFlag"], normalized_type),
        flag=flag_value,
        join_separator=join_separator,
        negate_flag=negate_flag,
        literal_values=literal_values,
        default=default_value,
    )


def _parse_target_selector(entry: JSONValue, *, context: str) -> _TargetSelector:
    """Create a target selector from catalog metadata.

    Args:
        entry: Raw JSON configuration for the selector.
        context: Human-readable context used for error reporting.

    Returns:
        _TargetSelector: Normalised selector configuration.

    Raises:
        CatalogIntegrityError: If required fields are missing or invalid.
    """

    if not isinstance(entry, Mapping):
        raise CatalogIntegrityError(f"{context}: target selector must be an object")

    mode_value = entry.get("type", "filePattern")
    if not isinstance(mode_value, str):
        raise CatalogIntegrityError(f"{context}: 'type' must be a string")
    normalized_mode = mode_value.strip()
    if normalized_mode != "filePattern":
        raise CatalogIntegrityError(f"{context}: unsupported target selector type '{mode_value}'")

    suffixes_value = entry.get("suffixes", ())
    if isinstance(suffixes_value, str):
        suffixes = (suffixes_value,)
    elif isinstance(suffixes_value, Sequence) and not isinstance(suffixes_value, (str, bytes, bytearray)):
        suffixes = tuple(str(item) for item in suffixes_value if item is not None)
    else:
        raise CatalogIntegrityError(f"{context}: 'suffixes' must be a string or array of strings")

    contains_value = entry.get("contains", ())
    if isinstance(contains_value, str):
        contains = (contains_value,)
    elif isinstance(contains_value, Sequence) and not isinstance(contains_value, (str, bytes, bytearray)):
        contains = tuple(str(item) for item in contains_value if item is not None)
    else:
        raise CatalogIntegrityError(f"{context}: 'contains' must be a string or array of strings")

    fallback_value = entry.get("fallbackDirectory")
    if fallback_value is None:
        fallback_directory: str | None = None
    elif isinstance(fallback_value, str) and fallback_value.strip():
        fallback_directory = fallback_value
    else:
        raise CatalogIntegrityError(f"{context}: 'fallbackDirectory' must be a non-empty string if provided")

    default_to_root_value = entry.get("defaultToRoot", False)
    if isinstance(default_to_root_value, bool):
        default_to_root = default_to_root_value
    else:
        raise CatalogIntegrityError(f"{context}: 'defaultToRoot' must be a boolean")

    return _TargetSelector(
        mode="filePattern",
        suffixes=suffixes,
        contains=contains,
        fallback_directory=fallback_directory,
        default_to_root=default_to_root,
    )


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
        """Return resolved command targets.

        Args:
            ctx: Tool execution context supplying settings and configuration.
            excluded: Paths that should be omitted from target selection.
            root: Repository root for resolving relative paths.

        Returns:
            list[str]: Ordered list of target arguments.
        """

        targets: set[Path] = set()
        for name in self.settings:
            for value in _settings_list(_setting(ctx.settings, name)):
                candidate = _resolve_path(root, value)
                if self.filter_excluded and _is_under_any(candidate, excluded):
                    continue
                targets.add(candidate)

        discovery = getattr(ctx.cfg, "file_discovery", None)
        if discovery is not None:
            if self.include_discovery_roots:
                for directory in discovery.roots:
                    resolved = directory if directory.is_absolute() else root / directory
                    if resolved == root:
                        continue
                    if self.filter_excluded and _is_under_any(resolved, excluded):
                        continue
                    targets.add(resolved)
            if self.include_discovery_explicit:
                for file_path in discovery.explicit_files:
                    resolved_file = file_path if file_path.is_absolute() else root / file_path
                    parent = resolved_file.parent
                    if self.filter_excluded and _is_under_any(parent, excluded):
                        continue
                    targets.add(parent)

        if not targets:
            for fallback in self.fallback_paths:
                candidate = _resolve_path(root, fallback)
                if fallback != "." and not candidate.exists():
                    continue
                if self.filter_excluded and _is_under_any(candidate, excluded):
                    continue
                targets.add(candidate)
                break

        if not targets and self.default_to_root:
            if not self.filter_excluded or not _is_under_any(root, excluded):
                targets.add(root)

        return sorted({str(path) for path in targets})


@dataclass(slots=True)
class _ProjectScannerStrategy(CommandBuilder):
    """Command builder orchestrating project-aware scanners."""

    base: tuple[str, ...]
    options: tuple[_CommandOption, ...]
    exclude_settings: tuple[str, ...]
    include_discovery_excludes: bool
    exclude_flag: str | None
    exclude_separator: str
    target_plan: _ProjectTargetPlan | None

    def build(self, ctx: ToolContext) -> Sequence[str]:
        """Compose the project scanner command for the provided context.

        Args:
            ctx: Tool execution context containing repository metadata and
                configured settings.

        Returns:
            Sequence[str]: Fully rendered command arguments.
        """

        root = ctx.root
        command = list(self.base)

        excluded_paths: set[Path] = set()
        for name in self.exclude_settings:
            for value in _settings_list(_setting(ctx.settings, name)):
                excluded_paths.add(_resolve_path(root, value))

        if self.include_discovery_excludes:
            discovery = getattr(ctx.cfg, "file_discovery", None)
            if discovery is not None:
                for path in discovery.excludes:
                    resolved = path if path.is_absolute() else root / path
                    excluded_paths.add(resolved)

        if self.exclude_flag and excluded_paths:
            exclude_args = _compile_exclude_arguments(excluded_paths, root)
            if exclude_args:
                command.extend([self.exclude_flag, self.exclude_separator.join(sorted(exclude_args))])

        for option in self.options:
            option.apply(ctx=ctx, command=command)

        if self.target_plan is not None:
            targets = self.target_plan.resolve(ctx, excluded=excluded_paths, root=root)
            if targets:
                if self.target_plan.prefix:
                    command.append(self.target_plan.prefix)
                command.extend(targets)

        return tuple(command)


def command_project_scanner(config: Mapping[str, JSONValue]) -> CommandBuilder:
    """Build a project-aware scanner command builder.

    Args:
        config: Catalog configuration describing the scanner’s base command,
            option mappings, exclusion behaviour, and target resolution plan.

    Returns:
        CommandBuilder: Strategy that produces commands aligned with the
        catalog-defined scanning workflow.

    Raises:
        CatalogIntegrityError: If the configuration is missing required fields or
            contains invalid values.
    """

    plain_config = cast(JSONValue, _as_plain_json(config))
    if not isinstance(plain_config, Mapping):
        raise CatalogIntegrityError("command_project_scanner: configuration must be an object")

    base_config = plain_config.get("base")
    if not isinstance(base_config, Sequence) or isinstance(base_config, (str, bytes, bytearray)):
        raise CatalogIntegrityError("command_project_scanner: 'base' must be an array of arguments")
    base_args = tuple(str(part) for part in base_config)
    if not base_args:
        raise CatalogIntegrityError("command_project_scanner: 'base' must contain at least one argument")

    options_config = plain_config.get("options")
    option_specs: list[_CommandOption] = []
    if options_config is not None:
        if not isinstance(options_config, Sequence) or isinstance(options_config, (str, bytes, bytearray)):
            raise CatalogIntegrityError("command_project_scanner: 'options' must be an array of objects")
        for index, entry in enumerate(options_config):
            option_specs.append(_parse_command_option(entry, index=index))

    exclude_config = plain_config.get("exclude", {})
    if not isinstance(exclude_config, Mapping):
        raise CatalogIntegrityError("command_project_scanner: 'exclude' must be an object when provided")
    exclude_settings_value = exclude_config.get("settings", ())
    if isinstance(exclude_settings_value, str):
        exclude_settings = (exclude_settings_value,)
    elif isinstance(exclude_settings_value, Sequence) and not isinstance(
        exclude_settings_value, (str, bytes, bytearray)
    ):
        exclude_settings = tuple(str(item) for item in exclude_settings_value if item is not None)
    else:
        raise CatalogIntegrityError("command_project_scanner: exclude.settings must be string or array of strings")

    include_discovery_excludes = bool(exclude_config.get("includeDiscovery", False))
    exclude_flag_value = exclude_config.get("flag")
    if exclude_flag_value is None:
        exclude_flag = None
    elif isinstance(exclude_flag_value, str):
        exclude_flag = exclude_flag_value
    else:
        raise CatalogIntegrityError("command_project_scanner: exclude.flag must be a string when provided")

    separator_value = exclude_config.get("separator", ",")
    if not isinstance(separator_value, str) or not separator_value:
        raise CatalogIntegrityError("command_project_scanner: exclude.separator must be a non-empty string")

    targets_config = plain_config.get("targets")
    target_plan = None
    if targets_config is not None:
        target_plan = _parse_project_target_plan(targets_config)

    return _ProjectScannerStrategy(
        base=base_args,
        options=tuple(option_specs),
        exclude_settings=exclude_settings,
        include_discovery_excludes=include_discovery_excludes,
        exclude_flag=exclude_flag,
        exclude_separator=separator_value,
        target_plan=target_plan,
    )


def _parse_project_target_plan(entry: JSONValue) -> _ProjectTargetPlan:
    """Create a project target plan from catalog data.

    Args:
        entry: Raw JSON configuration describing target selection.

    Returns:
        _ProjectTargetPlan: Parsed configuration used to resolve command
        targets at runtime.

    Raises:
        CatalogIntegrityError: If the configuration is malformed.
    """

    if not isinstance(entry, Mapping):
        raise CatalogIntegrityError("command_project_scanner.targets must be an object")

    settings_value = entry.get("settings", ())
    if isinstance(settings_value, str):
        settings = (settings_value,)
    elif isinstance(settings_value, Sequence) and not isinstance(settings_value, (str, bytes, bytearray)):
        settings = tuple(str(item) for item in settings_value if item is not None)
    else:
        raise CatalogIntegrityError("command_project_scanner.targets.settings must be string or array of strings")

    include_roots = bool(entry.get("includeDiscoveryRoots", False))
    include_explicit = bool(entry.get("includeDiscoveryExplicit", False))

    fallback_value = entry.get("fallback", ())
    if isinstance(fallback_value, str):
        fallback_paths = (fallback_value,)
    elif isinstance(fallback_value, Sequence) and not isinstance(fallback_value, (str, bytes, bytearray)):
        fallback_paths = tuple(str(item) for item in fallback_value if item is not None)
    else:
        raise CatalogIntegrityError("command_project_scanner.targets.fallback must be string or array of strings")

    default_to_root = bool(entry.get("defaultToRoot", False))
    filter_excluded = bool(entry.get("filterExcluded", True))

    prefix_value = entry.get("prefix")
    if prefix_value is None:
        prefix = None
    elif isinstance(prefix_value, str):
        prefix = prefix_value
    else:
        raise CatalogIntegrityError("command_project_scanner.targets.prefix must be a string when provided")

    return _ProjectTargetPlan(
        settings=settings,
        include_discovery_roots=include_roots,
        include_discovery_explicit=include_explicit,
        fallback_paths=fallback_paths,
        default_to_root=default_to_root,
        filter_excluded=filter_excluded,
        prefix=prefix,
    )


__all__ = ["command_download_binary", "command_project_scanner"]
