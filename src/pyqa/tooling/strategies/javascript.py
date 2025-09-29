"""JavaScript and TypeScript command strategies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from ..loader import CatalogIntegrityError
from ..tools.base import CommandBuilder, ToolContext
from ..tools.builtin_helpers import _as_bool, _resolve_path, _setting, _settings_list
from .common import _normalize_sequence, _require_string_sequence
from ..catalog.types import JSONValue


class _EslintStrategy(CommandBuilder):
    """Command builder accommodating ESLint lint and fix actions."""

    base: tuple[str, ...]
    is_fix: bool = False

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        for ext in _settings_list(_setting(settings, "ext", "extensions")):
            cmd.extend(["--ext", str(ext)])

        ignore_path = _setting(settings, "ignore-path", "ignore_path")
        if ignore_path:
            cmd.extend(["--ignore-path", str(_resolve_path(root, ignore_path))])

        resolve_plugins = _setting(
            settings,
            "resolve-plugins-relative-to",
            "resolve_plugins_relative_to",
        )
        if resolve_plugins:
            cmd.extend(
                [
                    "--resolve-plugins-relative-to",
                    str(_resolve_path(root, resolve_plugins)),
                ],
            )

        for directory in _settings_list(_setting(settings, "rulesdir", "rules-dir")):
            cmd.extend(["--rulesdir", str(_resolve_path(root, directory))])

        max_warnings = _setting(settings, "max-warnings", "max_warnings")
        if max_warnings is not None:
            cmd.extend(["--max-warnings", str(max_warnings)])

        cache_value = _as_bool(_setting(settings, "cache"))
        if cache_value is True:
            cmd.append("--cache")
        elif cache_value is False:
            cmd.append("--no-cache")

        cache_location = _setting(settings, "cache-location", "cache_location")
        if cache_location:
            cmd.extend(["--cache-location", str(_resolve_path(root, cache_location))])

        fix_type = _settings_list(_setting(settings, "fix-type", "fix_type"))
        if fix_type:
            cmd.extend(["--fix-type", ",".join(fix_type)])

        if _as_bool(_setting(settings, "quiet")):
            cmd.append("--quiet")

        no_error_unmatched = _as_bool(
            _setting(
                settings,
                "no-error-on-unmatched-pattern",
                "no_error_on_unmatched_pattern",
            ),
        )
        if no_error_unmatched is True:
            cmd.append("--no-error-on-unmatched-pattern")
        elif no_error_unmatched is False and not self.is_fix:
            cmd.append("--error-on-unmatched-pattern")

        report_unused = _setting(
            settings,
            "report-unused-disable-directives",
            "report_unused_disable_directives",
        )
        if report_unused:
            cmd.extend(
                [
                    "--report-unused-disable-directives",
                    str(report_unused),
                ],
            )

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


def eslint_command(config: Mapping[str, JSONValue]) -> CommandBuilder:
    """Return a command builder configured for ESLint."""

    base_args = _require_string_sequence(config, "base", context="command_eslint")
    is_fix_raw = config.get("isFix")
    if is_fix_raw is None:
        is_fix = False
    elif isinstance(is_fix_raw, bool):
        is_fix = is_fix_raw
    else:
        raise CatalogIntegrityError("command_eslint: 'isFix' must be a boolean when provided")
    return _EslintStrategy(base=base_args, is_fix=is_fix)


class _PrettierStrategy(CommandBuilder):
    """Command builder that mirrors Prettier CLI argument handling."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        parser = _setting(settings, "parser")
        if parser:
            cmd.extend(["--parser", str(parser)])

        ignore_path = _setting(settings, "ignore-path", "ignore_path")
        if ignore_path:
            cmd.extend(["--ignore-path", str(_resolve_path(root, ignore_path))])

        for directory in _settings_list(
            _setting(settings, "plugin-search-dir", "plugin_search_dir"),
        ):
            cmd.extend(["--plugin-search-dir", str(_resolve_path(root, directory))])

        for plugin in _settings_list(_setting(settings, "plugin", "plugins")):
            cmd.extend(["--plugin", str(plugin)])

        loglevel = _setting(settings, "loglevel")
        if loglevel:
            cmd.extend(["--log-level", str(loglevel)])

        precedence = _setting(settings, "config-precedence", "config_precedence")
        if precedence:
            cmd.extend(["--config-precedence", str(precedence)])

        single_quote = _as_bool(_setting(settings, "single-quote", "single_quote"))
        if single_quote is True:
            cmd.append("--single-quote")
        elif single_quote is False:
            cmd.append("--no-single-quote")

        tab_width = _setting(settings, "tab-width", "tab_width")
        if tab_width is not None:
            cmd.extend(["--tab-width", str(tab_width)])

        use_tabs = _as_bool(_setting(settings, "use-tabs", "use_tabs"))
        if use_tabs is True:
            cmd.append("--use-tabs")
        elif use_tabs is False:
            cmd.append("--no-use-tabs")

        trailing_comma = _setting(settings, "trailing-comma", "trailing_comma")
        if trailing_comma:
            cmd.extend(["--trailing-comma", str(trailing_comma)])

        print_width = _setting(settings, "print-width", "print_width")
        if print_width is None:
            print_width = ctx.cfg.execution.line_length
        if print_width is not None:
            cmd.extend(["--print-width", str(print_width)])

        semi = _as_bool(_setting(settings, "semi"))
        if semi is True:
            cmd.append("--semi")
        elif semi is False:
            cmd.append("--no-semi")

        end_of_line = _setting(settings, "end-of-line", "end_of_line")
        if end_of_line:
            cmd.extend(["--end-of-line", str(end_of_line)])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


def prettier_command(config: Mapping[str, JSONValue]) -> CommandBuilder:
    """Return a command builder configured for Prettier."""

    base_args = _require_string_sequence(config, "base", context="command_prettier")
    return _PrettierStrategy(base=base_args)


class _RemarkLintStrategy(CommandBuilder):
    """Command builder that mirrors remark-lint CLI behaviour."""

    base: tuple[str, ...]
    is_fix: bool = False

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        if not self.is_fix and "--report" not in cmd:
            cmd.extend(["--report", "json"])
        if not self.is_fix and "--frail" not in cmd:
            cmd.append("--frail")
        if not self.is_fix and "--quiet" not in cmd:
            cmd.append("--quiet")
        if not self.is_fix and "--no-color" not in cmd:
            cmd.append("--no-color")

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        for plugin in _settings_list(_setting(settings, "use")):
            cmd.extend(["--use", str(plugin)])

        ignore_path = _setting(settings, "ignore-path", "ignore_path")
        if ignore_path:
            cmd.extend(["--ignore-path", str(_resolve_path(root, ignore_path))])

        for value in _settings_list(_setting(settings, "setting")):
            cmd.extend(["--setting", str(value)])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        files = [str(path) for path in ctx.files]
        if files:
            cmd.extend(files)
        elif self.is_fix:
            cmd.append(str(root))
        if self.is_fix and "--output" not in cmd and "-o" not in cmd:
            cmd.append("--output")

        return tuple(cmd)


def remark_lint_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for remark-lint."""

    base_args = _require_string_sequence(config, "base", context="command_remark_lint")
    is_fix_raw = config.get("isFix")
    if is_fix_raw is None:
        is_fix = False
    elif isinstance(is_fix_raw, bool):
        is_fix = is_fix_raw
    else:
        raise CatalogIntegrityError("command_remark_lint: 'isFix' must be a boolean when provided")
    return _RemarkLintStrategy(base=base_args, is_fix=is_fix)


class _StylelintStrategy(CommandBuilder):
    """Command builder for stylelint supporting lint and fix modes."""

    base: tuple[str, ...]
    is_fix: bool = False

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        config_basedir = _setting(settings, "config-basedir", "config_basedir")
        if config_basedir:
            cmd.extend(["--config-basedir", str(_resolve_path(root, config_basedir))])

        ignore_path = _setting(settings, "ignore-path", "ignore_path")
        if ignore_path:
            cmd.extend(["--ignore-path", str(_resolve_path(root, ignore_path))])

        custom_syntax = _setting(settings, "custom-syntax", "custom_syntax")
        if custom_syntax:
            cmd.extend(["--custom-syntax", str(custom_syntax)])

        if _as_bool(_setting(settings, "allow-empty-input", "allow_empty_input")):
            cmd.append("--allow-empty-input")

        if _as_bool(_setting(settings, "disable-default-ignores", "disable_default_ignores")):
            cmd.append("--disable-default-ignores")

        if _as_bool(_setting(settings, "quiet")):
            cmd.append("--quiet")

        max_warnings = _setting(settings, "max-warnings", "max_warnings")
        if max_warnings is not None:
            cmd.extend(["--max-warnings", str(max_warnings)])

        if not self.is_fix and "--formatter" not in cmd and "--custom-formatter" not in cmd:
            cmd.extend(["--formatter", "json"])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


def command_stylelint(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for stylelint."""

    base_config = config.get("base")
    if base_config is None:
        base_args = ("stylelint",)
    else:
        base_tuple = _normalize_sequence(base_config)
        if not base_tuple:
            raise CatalogIntegrityError("command_stylelint: 'base' must contain at least one argument")
        base_args = tuple(str(part) for part in base_tuple)

    is_fix_value = config.get("isFix")
    if isinstance(is_fix_value, bool):
        is_fix = is_fix_value
    elif is_fix_value is None:
        is_fix = False
    else:
        raise CatalogIntegrityError("command_stylelint: 'isFix' must be a boolean")

    return _StylelintStrategy(base=base_args, is_fix=is_fix)


__all__ = [
    "command_stylelint",
    "eslint_command",
    "gts_command",
    "prettier_command",
    "remark_lint_command",
    "tsc_command",
]


class _GtsStrategy(CommandBuilder):
    """Command builder replicating gts CLI behaviour."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        project = _setting(settings, "project")
        if project:
            cmd.extend(["--project", str(_resolve_path(root, project))])

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        extra = _settings_list(_setting(settings, "args"))
        if extra:
            cmd.extend(str(arg) for arg in extra)
        return tuple(cmd)


def gts_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for gts."""

    base_args = _require_string_sequence(config, "base", context="command_gts")
    return _GtsStrategy(base=base_args)


class _TscStrategy(CommandBuilder):
    """Command builder providing TypeScript compiler arguments."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        project = _setting(settings, "project")
        if project:
            cmd.extend(["--project", str(_resolve_path(root, project))])

        pretty = _setting(settings, "pretty")
        if pretty is not None:
            cmd.extend(["--pretty", "true" if _as_bool(pretty) else "false"])

        if _as_bool(_setting(settings, "incremental")):
            cmd.append("--incremental")
        if _as_bool(_setting(settings, "watch")):
            cmd.append("--watch")
        if _as_bool(_setting(settings, "skip-lib-check", "skip_lib_check")):
            cmd.append("--skipLibCheck")
        if _as_bool(_setting(settings, "strict")):
            cmd.append("--strict")

        extra = _settings_list(_setting(settings, "args"))
        if extra:
            cmd.extend(str(arg) for arg in extra)
        return tuple(cmd)


def tsc_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for tsc."""

    base_args = _require_string_sequence(config, "base", context="command_tsc")
    return _TscStrategy(base=base_args)
