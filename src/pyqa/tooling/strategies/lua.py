"""Lua ecosystem command strategies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from ..loader import CatalogIntegrityError
from ..tools.base import CommandBuilder, ToolContext
from ..tools.builtin_helpers import _as_bool, _resolve_path, _setting, _settings_list
from .common import (
    _download_artifact_for_tool,
    _require_string_sequence,
)
from ..catalog.types import JSONValue


class _SeleneStrategy(CommandBuilder):
    """Command builder tailored for the Selene Lua linter."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        display_style = _setting(settings, "display-style", "display_style")
        if not display_style:
            display_style = "Json2"
        cmd.extend(["--display-style", str(display_style)])

        color = _setting(settings, "color")
        if not color:
            color = "Never"
        cmd.extend(["--color", str(color)])

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        for pattern in _settings_list(_setting(settings, "pattern")):
            cmd.extend(["--pattern", str(pattern)])

        num_threads = _setting(settings, "num-threads", "num_threads")
        if num_threads is not None:
            cmd.extend(["--num-threads", str(num_threads)])

        if _as_bool(_setting(settings, "allow-warnings", "allow_warnings")):
            cmd.append("--allow-warnings")

        if _as_bool(_setting(settings, "no-exclude", "no_exclude")):
            cmd.append("--no-exclude")

        if _as_bool(_setting(settings, "quiet")):
            cmd.append("--quiet")

        if _as_bool(_setting(settings, "no-summary", "no_summary")):
            cmd.append("--no-summary")

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


def selene_command(config: Mapping[str, JSONValue]) -> CommandBuilder:
    """Return a command builder configured for Selene."""

    base_args = _require_string_sequence(config, "base", context="command_selene")
    return _SeleneStrategy(base=base_args)


class _LualintStrategy(CommandBuilder):
    """Command builder that invokes the lualint shim."""

    base: tuple[str, ...]
    download: Mapping[str, JSONValue]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cache_root = ctx.root / ".lint-cache"
        script = _download_artifact_for_tool(
            self.download,
            version=None,
            cache_root=cache_root,
            context="command_lualint.download",
        )
        cmd = list(self.base)
        cmd.append(str(script))

        relaxed = _as_bool(_setting(ctx.settings, "relaxed"))
        strict = _as_bool(_setting(ctx.settings, "strict"))
        if relaxed:
            cmd.append("-r")
        if strict:
            cmd.append("-s")

        extra = _settings_list(_setting(ctx.settings, "args"))
        if extra:
            cmd.extend(str(arg) for arg in extra)
        return tuple(cmd)


def lualint_command(config: Mapping[str, JSONValue]) -> CommandBuilder:
    """Return a command builder configured for lualint."""

    base_args = _require_string_sequence(config, "base", context="command_lualint")
    download_config = config.get("download")
    if not isinstance(download_config, Mapping):
        raise CatalogIntegrityError("command_lualint: missing 'download' configuration")
    download_mapping = cast(Mapping[str, JSONValue], download_config)
    return _LualintStrategy(base=base_args, download=download_mapping)


class _LuacheckStrategy(CommandBuilder):
    """Command builder that mirrors luacheck CLI behaviour."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)

        def ensure_flag(flag: str, *values: str) -> None:
            if flag not in cmd:
                cmd.append(flag)
                cmd.extend(values)

        ensure_flag("--formatter", "plain")
        if "--codes" not in cmd:
            cmd.append("--codes")
        if "--ranges" not in cmd:
            cmd.append("--ranges")
        if "--no-color" not in cmd:
            cmd.append("--no-color")

        root = ctx.root
        settings = ctx.settings

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        line_length = _setting(settings, "max-line-length", "max_line_length")
        if line_length is None:
            line_length = ctx.cfg.execution.line_length
        if line_length is not None:
            ensure_flag("--max-line-length", str(line_length))

        max_code_length = _setting(settings, "max-code-line-length", "max_code_line_length")
        if max_code_length is None:
            max_code_length = line_length
        if max_code_length is not None:
            ensure_flag("--max-code-line-length", str(max_code_length))

        max_string_length = _setting(settings, "max-string-line-length", "max_string_line_length")
        if max_string_length is None:
            max_string_length = line_length
        if max_string_length is not None:
            ensure_flag("--max-string-line-length", str(max_string_length))

        max_comment_length = _setting(settings, "max-comment-line-length", "max_comment_line_length")
        if max_comment_length is None:
            max_comment_length = line_length
        if max_comment_length is not None:
            ensure_flag("--max-comment-line-length", str(max_comment_length))

        max_cyclomatic = _setting(settings, "max-cyclomatic-complexity", "max_cyclomatic_complexity")
        if max_cyclomatic is None:
            max_cyclomatic = ctx.cfg.complexity.max_complexity
        if max_cyclomatic is not None:
            ensure_flag("--max-cyclomatic-complexity", str(max_cyclomatic))

        std = _setting(settings, "std")
        if std:
            cmd.extend(["--std", str(std)])

        globals_list = _settings_list(_setting(settings, "globals"))
        if globals_list:
            cmd.extend(["--globals", ",".join(globals_list)])

        read_globals = _settings_list(_setting(settings, "read-globals", "read_globals"))
        if read_globals:
            cmd.extend(["--read-globals", ",".join(read_globals)])

        ignore = _settings_list(_setting(settings, "ignore"))
        if ignore:
            cmd.extend(["--ignore", ",".join(ignore)])

        exclude = _settings_list(_setting(settings, "exclude-files", "exclude_files"))
        for value in exclude:
            cmd.extend(["--exclude-files", str(_resolve_path(root, value))])

        if _as_bool(_setting(settings, "quiet")):
            cmd.append("--quiet")

        extra = _settings_list(_setting(settings, "args"))
        if extra:
            cmd.extend(str(arg) for arg in extra)

        return tuple(cmd)


def luacheck_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for luacheck."""

    base_args = _require_string_sequence(config, "base", context="command_luacheck")
    return _LuacheckStrategy(base=base_args)


__all__ = [
    "lualint_command",
    "luacheck_command",
    "selene_command",
]
