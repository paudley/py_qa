# SPDX-License-Identifier: MIT
"""Command builder implementations for built-in tools."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .base import CommandBuilder, ToolContext
from .builtin_helpers import (
    _as_bool,
    _resolve_path,
    _setting,
    _settings_list,
    ensure_actionlint,
    ensure_hadolint,
    ensure_lualint,
)


@dataclass(slots=True)
class _PerltidyCommand(CommandBuilder):
    base: Sequence[str]
    is_fix: bool = False

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        profile = _setting(settings, "profile", "configuration")
        if profile:
            cmd.extend(["--profile", str(_resolve_path(root, profile))])

        extra = _settings_list(_setting(settings, "args"))
        if extra:
            cmd.extend(str(arg) for arg in extra)

        if self.is_fix:
            if "-b" not in cmd:
                cmd.extend(["-b", '-bext=""'])
            if "-q" not in cmd:
                cmd.append("-q")
        else:
            if "--check-only" not in cmd:
                cmd.append("--check-only")
            if "-q" not in cmd:
                cmd.append("-q")

        return tuple(cmd)


@dataclass(slots=True)
class _PerlCriticCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        if "--nocolor" not in cmd:
            cmd.append("--nocolor")
        if "--verbose" not in cmd:
            cmd.extend(["--verbose", "%f:%l:%c:%m (%p)"])

        severity = _setting(settings, "severity")
        if severity:
            cmd.extend(["--severity", str(severity)])

        theme = _setting(settings, "theme")
        if theme:
            cmd.extend(["--theme", str(theme)])

        profile = _setting(settings, "profile", "configuration")
        if profile:
            cmd.extend(["--profile", str(_resolve_path(root, profile))])

        include = _settings_list(_setting(settings, "include"))
        for policy in include:
            cmd.extend(["--include", str(policy)])

        exclude = _settings_list(_setting(settings, "exclude"))
        for policy in exclude:
            cmd.extend(["--exclude", str(policy)])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _EslintCommand(CommandBuilder):
    base: Sequence[str]
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

        cache = _as_bool(_setting(settings, "cache"))
        if cache is True:
            cmd.append("--cache")
        elif cache is False:
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


@dataclass(slots=True)
class _PrettierCommand(CommandBuilder):
    base: Sequence[str]

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

        config_precedence = _setting(settings, "config-precedence", "config_precedence")
        if config_precedence:
            cmd.extend(["--config-precedence", str(config_precedence)])

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


@dataclass(slots=True)
class _ActionlintCommand(CommandBuilder):
    version: str

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cache_root = ctx.root / ".lint-cache"
        binary = ensure_actionlint(self.version, cache_root)
        cmd = [str(binary), "-format", "{{json .}}", "-no-color"]

        workflow_files = [
            path
            for path in ctx.files
            if str(path).endswith(".yml") and "/.github/workflows/" in str(path)
        ]
        if workflow_files:
            cmd.extend(str(path) for path in workflow_files)
        else:
            workflows_dir = ctx.root / ".github" / "workflows"
            if workflows_dir.exists():
                cmd.append(str(workflows_dir))
            else:
                cmd.append(str(ctx.root))

        return tuple(cmd)


@dataclass(slots=True)
class _KubeLinterCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)

        root = ctx.root
        settings = ctx.settings

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        if _as_bool(_setting(settings, "fail-if-no-objects-found")):
            cmd.append("--fail-if-no-objects-found")

        if _as_bool(_setting(settings, "fail-on-invalid-resource")):
            cmd.append("--fail-on-invalid-resource")

        if _as_bool(_setting(settings, "verbose")):
            cmd.append("--verbose")

        if _as_bool(_setting(settings, "add-all-built-in")):
            cmd.append("--add-all-built-in")

        if _as_bool(_setting(settings, "do-not-auto-add-defaults")):
            cmd.append("--do-not-auto-add-defaults")

        for include in _settings_list(_setting(settings, "include")):
            cmd.extend(["--include", str(include)])

        for exclude in _settings_list(_setting(settings, "exclude")):
            cmd.extend(["--exclude", str(exclude)])

        for path in _settings_list(_setting(settings, "ignore-paths", "ignore_paths")):
            cmd.extend(["--ignore-paths", str(_resolve_path(root, path))])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _StylelintCommand(CommandBuilder):
    base: Sequence[str]
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


@dataclass(slots=True)
class _YamllintCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config_file = _setting(settings, "config-file", "config_file")
        if config_file:
            cmd.extend(["--config-file", str(_resolve_path(root, config_file))])

        config_data = _setting(settings, "config-data", "config_data")
        if config_data:
            cmd.extend(["--config-data", str(config_data)])

        if _as_bool(_setting(settings, "strict")):
            cmd.append("--strict")

        if "--format" not in cmd and "-f" not in cmd:
            cmd.extend(["--format", "parsable"])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _DockerfilelintCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _HadolintCommand(CommandBuilder):
    version: str

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cache_root = ctx.root / ".lint-cache"
        binary = ensure_hadolint(self.version, cache_root)
        cmd = [str(binary), "--format", "json"]

        config = _setting(ctx.settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(ctx.root, config))])

        failure_threshold = _setting(ctx.settings, "failure-threshold", "failure_threshold")
        if failure_threshold:
            cmd.extend(["--failure-threshold", str(failure_threshold)])

        args = _settings_list(_setting(ctx.settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _DotenvLinterCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        if "--no-color" not in cmd:
            cmd.append("--no-color")
        if "--quiet" not in cmd:
            cmd.append("--quiet")

        root = ctx.root
        settings = ctx.settings

        for exclude in _settings_list(_setting(settings, "exclude")):
            cmd.extend(["--exclude", str(_resolve_path(root, exclude))])

        for skip in _settings_list(_setting(settings, "skip")):
            cmd.extend(["--skip", str(skip)])

        schema = _setting(settings, "schema")
        if schema:
            cmd.extend(["--schema", str(_resolve_path(root, schema))])

        if _as_bool(_setting(settings, "recursive")):
            cmd.append("--recursive")

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _LualintCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cache_root = ctx.root / ".lint-cache"
        script = ensure_lualint(cache_root)
        cmd = list(self.base)
        cmd.append(str(script))

        relaxed = _as_bool(_setting(ctx.settings, "relaxed"))
        strict = _as_bool(_setting(ctx.settings, "strict"))
        if relaxed:
            cmd.append("-r")
        if strict:
            cmd.append("-s")

        args = _settings_list(_setting(ctx.settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _LuacheckCommand(CommandBuilder):
    base: Sequence[str]

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

        max_comment_length = _setting(
            settings,
            "max-comment-line-length",
            "max_comment_line_length",
        )
        if max_comment_length is None:
            max_comment_length = line_length
        if max_comment_length is not None:
            ensure_flag("--max-comment-line-length", str(max_comment_length))

        max_cyclomatic = _setting(
            settings,
            "max-cyclomatic-complexity",
            "max_cyclomatic_complexity",
        )
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

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _SeleneCommand(CommandBuilder):
    base: Sequence[str]

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


@dataclass(slots=True)
class _RemarkCommand(CommandBuilder):
    base: Sequence[str]
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

        use_plugins = _settings_list(_setting(settings, "use"))
        for plugin in use_plugins:
            cmd.extend(["--use", str(plugin)])

        ignore_path = _setting(settings, "ignore-path", "ignore_path")
        if ignore_path:
            cmd.extend(["--ignore-path", str(_resolve_path(root, ignore_path))])

        setting_files = _settings_list(_setting(settings, "setting"))
        for value in setting_files:
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


@dataclass(slots=True)
class _SpeccyCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        if "--reporter" not in cmd:
            cmd.extend(["--reporter", "json"])

        ruleset = _setting(settings, "ruleset")
        if ruleset:
            cmd.extend(["--ruleset", str(_resolve_path(root, ruleset))])

        skip = _settings_list(_setting(settings, "skip"))
        for value in skip:
            cmd.extend(["--skip", str(value)])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _ShfmtCommand(CommandBuilder):
    base: Sequence[str]
    is_fix: bool = False

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        settings = ctx.settings

        indent = _setting(settings, "indent", "spaces")
        if indent is not None and "-i" not in cmd:
            cmd.extend(["-i", str(indent)])

        language = _setting(settings, "language")
        if language and "-ln" not in cmd:
            cmd.extend(["-ln", str(language)])

        indent_case = _as_bool(_setting(settings, "indent-case", "indent_case"))
        if indent_case:
            cmd.append("-ci")

        simplify = _as_bool(_setting(settings, "simplify"))
        if simplify is True and "-s" not in cmd:
            cmd.append("-s")

        write_cmd = _as_bool(_setting(settings, "write"))
        if self.is_fix or write_cmd:
            cmd.append("-w")
        else:
            cmd.append("-d")

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _CheckmakeCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        if "--format" not in cmd and "-f" not in cmd:
            cmd.extend(["--format", "json"])

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        ignore = _settings_list(_setting(settings, "ignore"))
        for rule in ignore:
            cmd.extend(["--ignore", str(rule)])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _TscCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        project = _setting(settings, "project")
        if project:
            cmd.extend(["--project", str(_resolve_path(root, project))])

        pretty = _as_bool(_setting(settings, "pretty"))
        if pretty is True:
            cmd.extend(["--pretty", "true"])
        elif pretty is False:
            cmd.extend(["--pretty", "false"])

        if _as_bool(_setting(settings, "incremental")):
            cmd.append("--incremental")

        if _as_bool(_setting(settings, "watch")):
            cmd.append("--watch")

        if _as_bool(_setting(settings, "skip-lib-check", "skip_lib_check")):
            cmd.append("--skipLibCheck")

        if _as_bool(_setting(settings, "strict")):
            cmd.append("--strict")

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _PhplintCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        if "--no-ansi" not in cmd:
            cmd.append("--no-ansi")
        if "--no-progress" not in cmd:
            cmd.append("--no-progress")

        config = _setting(settings, "configuration", "config")
        if config:
            cmd.extend(["--configuration", str(_resolve_path(root, config))])

        exclude = _settings_list(_setting(settings, "exclude"))
        for path in exclude:
            cmd.extend(["--exclude", str(_resolve_path(root, path))])

        include = _settings_list(_setting(settings, "include"))
        for path in include:
            cmd.extend(["--include", str(_resolve_path(root, path))])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _GolangciLintCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        deadline = _setting(settings, "deadline")
        if deadline:
            cmd.extend(["--deadline", str(deadline)])

        enable_all_setting = _setting(settings, "enable-all", "enable_all")
        if enable_all_setting is None or _as_bool(enable_all_setting) is not False:
            if "--enable-all" not in cmd:
                cmd.append("--enable-all")

        for item in _settings_list(_setting(settings, "enable")):
            cmd.extend(["--enable", str(item)])

        for item in _settings_list(_setting(settings, "disable")):
            cmd.extend(["--disable", str(item)])

        tests = _as_bool(_setting(settings, "tests"))
        if tests is not None:
            cmd.extend(["--tests", "true" if tests else "false"])

        issues_exit_code = _setting(settings, "issues-exit-code", "issues_exit_code")
        if issues_exit_code is not None:
            cmd.extend(["--issues-exit-code", str(issues_exit_code)])

        build_tags = _settings_list(_setting(settings, "build-tags", "build_tags"))
        if build_tags:
            cmd.extend(["--build-tags", ",".join(build_tags)])

        for pattern in _settings_list(_setting(settings, "skip-files", "skip_files")):
            cmd.extend(["--skip-files", str(pattern)])

        for pattern in _settings_list(_setting(settings, "skip-dirs", "skip_dirs")):
            cmd.extend(["--skip-dirs", str(pattern)])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _GtsCommand(CommandBuilder):
    base: Sequence[str]
    is_fix: bool = False

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

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


__all__ = [
    "_ActionlintCommand",
    "_CheckmakeCommand",
    "_DockerfilelintCommand",
    "_DotenvLinterCommand",
    "_EslintCommand",
    "_GolangciLintCommand",
    "_GtsCommand",
    "_HadolintCommand",
    "_KubeLinterCommand",
    "_LuacheckCommand",
    "_LualintCommand",
    "_PerlCriticCommand",
    "_PerltidyCommand",
    "_PhplintCommand",
    "_PrettierCommand",
    "_RemarkCommand",
    "_SeleneCommand",
    "_ShfmtCommand",
    "_SpeccyCommand",
    "_StylelintCommand",
    "_TscCommand",
    "_YamllintCommand",
]
