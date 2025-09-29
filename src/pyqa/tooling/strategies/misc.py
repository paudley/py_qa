"""Miscellaneous command strategies covering mixed ecosystems."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..loader import CatalogIntegrityError
from ..tools.base import CommandBuilder, ToolContext
from ..tools.builtin_helpers import _as_bool, _resolve_path, _setting, _settings_list
from .common import _normalize_sequence, _require_string_sequence


class _GolangciLintStrategy(CommandBuilder):
    """Command builder that replicates golangci-lint CLI behaviour."""

    base: tuple[str, ...]

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

def golangci_lint_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for golangci-lint."""

    base_args = _require_string_sequence(config, "base", context="command_golangci_lint")
    return _GolangciLintStrategy(base=base_args)

class _YamllintStrategy(CommandBuilder):
    """Command builder that mirrors yamllint CLI behaviour."""

    base: tuple[str, ...]

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

        files = [str(path) for path in ctx.files]
        if files:
            cmd.extend(files)

        return tuple(cmd)

def yamllint_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for yamllint."""

    base_args = _require_string_sequence(config, "base", context="command_yamllint")
    return _YamllintStrategy(base=base_args)

class _SpeccyStrategy(CommandBuilder):
    """Command builder that configures Speccy lint invocations."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        if "--reporter" not in cmd:
            cmd.extend(["--reporter", "json"])

        ruleset = _setting(settings, "ruleset")
        if ruleset:
            cmd.extend(["--ruleset", str(_resolve_path(root, ruleset))])

        for value in _settings_list(_setting(settings, "skip")):
            cmd.extend(["--skip", str(value)])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        files = [str(path) for path in ctx.files]
        if files:
            cmd.extend(files)

        return tuple(cmd)

def speccy_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for Speccy."""

    base_args = _require_string_sequence(config, "base", context="command_speccy")
    return _SpeccyStrategy(base=base_args)

class _DotenvLinterStrategy(CommandBuilder):
    """Command builder that mirrors dotenv-linter argument handling."""

    base: tuple[str, ...]

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

def dotenv_linter_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for dotenv-linter."""

    base_config = config.get("base")
    if base_config is None:
        base_args = ("dotenv-linter",)
    else:
        base_tuple = _normalize_sequence(base_config)
        if not base_tuple:
            raise CatalogIntegrityError("dotenv_linter_command: 'base' must contain at least one argument")
        base_args = tuple(str(part) for part in base_tuple)
    return _DotenvLinterStrategy(base=base_args)

class _PerltidyStrategy(CommandBuilder):
    """Command builder providing perltidy arguments."""

    base: tuple[str, ...]
    is_fix: bool

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

def perltidy_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for perltidy."""

    base_args = _require_string_sequence(config, "base", context="command_perltidy")
    is_fix_value = config.get("isFix")
    is_fix = bool(is_fix_value) if isinstance(is_fix_value, bool) else False
    return _PerltidyStrategy(base=base_args, is_fix=is_fix)

class _PerlCriticStrategy(CommandBuilder):
    """Command builder providing perlcritic arguments."""

    base: tuple[str, ...]

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

        for policy in _settings_list(_setting(settings, "include")):
            cmd.extend(["--include", str(policy)])

        for policy in _settings_list(_setting(settings, "exclude")):
            cmd.extend(["--exclude", str(policy)])

        extra = _settings_list(_setting(settings, "args"))
        if extra:
            cmd.extend(str(arg) for arg in extra)

        return tuple(cmd)

def perlcritic_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for perlcritic."""

    base_args = _require_string_sequence(config, "base", context="command_perlcritic")
    return _PerlCriticStrategy(base=base_args)

class _PhplintStrategy(CommandBuilder):
    """Command builder handling phplint options."""

    base: tuple[str, ...]

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

        for path in _settings_list(_setting(settings, "exclude")):
            cmd.extend(["--exclude", str(_resolve_path(root, path))])

        for path in _settings_list(_setting(settings, "include")):
            cmd.extend(["--include", str(_resolve_path(root, path))])

        extra = _settings_list(_setting(settings, "args"))
        if extra:
            cmd.extend(str(arg) for arg in extra)

        return tuple(cmd)

def phplint_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for phplint."""

    base_args = _require_string_sequence(config, "base", context="command_phplint")
    return _PhplintStrategy(base=base_args)

class _DockerfilelintStrategy(CommandBuilder):
    """Command builder for dockerfilelint."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        config = _setting(ctx.settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])
        extra = _settings_list(_setting(ctx.settings, "args"))
        if extra:
            cmd.extend(str(arg) for arg in extra)
        return tuple(cmd)

def dockerfilelint_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for dockerfilelint."""

    base_args = _require_string_sequence(config, "base", context="command_dockerfilelint")
    return _DockerfilelintStrategy(base=base_args)

class _CheckmakeStrategy(CommandBuilder):
    """Command builder for checkmake."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings
        if "--format" not in cmd and "-f" not in cmd:
            cmd.extend(["--format", "json"])
        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])
        for rule in _settings_list(_setting(settings, "ignore")):
            cmd.extend(["--ignore", str(rule)])
        extra = _settings_list(_setting(settings, "args"))
        if extra:
            cmd.extend(str(arg) for arg in extra)
        return tuple(cmd)

def checkmake_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for checkmake."""

    base_args = _require_string_sequence(config, "base", context="command_checkmake")
    return _CheckmakeStrategy(base=base_args)

class _CpplintStrategy(CommandBuilder):
    """Command builder providing cpplint options."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        line_length = _setting(settings, "linelength", "line-length")
        if line_length is None:
            line_length = ctx.cfg.execution.line_length
        if line_length is not None:
            cmd.append(f"--linelength={line_length}")

        for value in _settings_list(_setting(settings, "filter")):
            cmd.append(f"--filter={value}")

        for path in _settings_list(_setting(settings, "exclude")):
            cmd.append(f"--exclude={_resolve_path(root, path)}")

        extensions = _settings_list(_setting(settings, "extensions"))
        if extensions:
            cmd.append(f"--extensions={','.join(str(ext) for ext in extensions)}")

        headers = _settings_list(_setting(settings, "headers"))
        if headers:
            cmd.append(f"--headers={','.join(str(h) for h in headers)}")

        include_order = _setting(settings, "includeorder")
        if include_order:
            cmd.append(f"--includeorder={include_order}")

        counting = _setting(settings, "counting")
        if counting:
            cmd.append(f"--counting={counting}")

        repository = _setting(settings, "repository")
        if repository:
            cmd.append(f"--repository={_resolve_path(root, repository)}")

        root_flag = _setting(settings, "root")
        if root_flag:
            cmd.append(f"--root={_resolve_path(root, root_flag)}")

        if _as_bool(_setting(settings, "recursive")):
            cmd.append("--recursive")
        if _as_bool(_setting(settings, "quiet")):
            cmd.append("--quiet")

        extra = _settings_list(_setting(settings, "args"))
        if extra:
            cmd.extend(str(arg) for arg in extra)
        return tuple(cmd)

def cpplint_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for cpplint."""

    base_args = _require_string_sequence(config, "base", context="command_cpplint")
    return _CpplintStrategy(base=base_args)


__all__ = [
    "checkmake_command",
    "cpplint_command",
    "dockerfilelint_command",
    "dot_env_linter_command"? -- wait, actual function is dotenv_linter_command;
