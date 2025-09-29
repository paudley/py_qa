"""Python ecosystem command strategies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..loader import CatalogIntegrityError
from ..tools.base import CommandBuilder, ToolContext
from ..tools.builtin_commands_python import (
    _discover_pylint_plugins,
    _python_target_version,
    _python_version_number,
    _python_version_tag,
    _pyupgrade_flag_from_version,
)
from ..tools.builtin_helpers import _as_bool, _resolve_path, _setting, _settings_list
from .common import _normalize_sequence, _require_str, _require_string_sequence


class _RuffStrategy(CommandBuilder):
    """Command builder wrapping ruff lint/fix behaviour."""

    base: tuple[str, ...]
    mode: str

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        for option in ("select", "ignore", "extend-select", "extend-ignore"):
            values = _settings_list(_setting(settings, option))
            if values:
                cmd.extend([f"--{option}", ",".join(values)])

        line_length = _setting(settings, "line-length")
        if line_length is None:
            line_length = ctx.cfg.execution.line_length
        if line_length is not None:
            cmd.extend(["--line-length", str(line_length)])

        target_version = _setting(settings, "target-version")
        if target_version:
            cmd.extend(["--target-version", str(target_version)])
        else:
            cmd.extend(["--target-version", _python_version_tag(_python_target_version(ctx))])

        per_file_ignores = _settings_list(_setting(settings, "per-file-ignores"))
        if per_file_ignores:
            cmd.extend(["--per-file-ignores", ";".join(per_file_ignores)])

        exclude = _settings_list(_setting(settings, "exclude"))
        if exclude:
            cmd.extend(["--exclude", ",".join(exclude)])

        extend_exclude = _settings_list(_setting(settings, "extend-exclude"))
        if extend_exclude:
            cmd.extend(["--extend-exclude", ",".join(extend_exclude)])

        respect_gitignore = _as_bool(_setting(settings, "respect-gitignore"))
        if respect_gitignore is True:
            cmd.append("--respect-gitignore")
        elif respect_gitignore is False:
            cmd.append("--no-respect-gitignore")

        preview = _as_bool(_setting(settings, "preview"))
        if preview is True:
            cmd.append("--preview")
        elif preview is False:
            cmd.append("--no-preview")

        if _as_bool(_setting(settings, "unsafe-fixes")):
            cmd.append("--unsafe-fixes")

        if self.mode == "lint":
            if _as_bool(_setting(settings, "fix")):
                cmd.append("--fix")
        elif _as_bool(_setting(settings, "fix")) is False:
            cmd = [part for part in cmd if part != "--fix"]

        additional_args = _settings_list(_setting(settings, "args"))
        if additional_args:
            cmd.extend(str(arg) for arg in additional_args)

        return tuple(cmd)


def ruff_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for ruff lint/fix runs."""

    base_args = _require_string_sequence(config, "base", context="command_ruff")
    mode_value = _require_str(config, "mode", context="command_ruff")
    if mode_value not in {"lint", "fix"}:
        raise CatalogIntegrityError("command_ruff: 'mode' must be 'lint' or 'fix'")
    return _RuffStrategy(base=base_args, mode=mode_value)


class _RuffFormatStrategy(CommandBuilder):
    """Command builder that wraps ruff format invocations."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        line_length = _setting(settings, "line-length")
        if line_length is None:
            line_length = ctx.cfg.execution.line_length
        if line_length is not None:
            cmd.extend(["--line-length", str(line_length)])

        target_version = _setting(settings, "target-version")
        if target_version:
            cmd.extend(["--target-version", str(target_version)])
        else:
            cmd.extend(["--target-version", _python_version_tag(_python_target_version(ctx))])

        additional_args = _settings_list(_setting(settings, "args"))
        if additional_args:
            cmd.extend(str(arg) for arg in additional_args)

        return tuple(cmd)


def ruff_format_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for ruff format actions."""

    base_args = _require_string_sequence(config, "base", context="command_ruff_format")
    return _RuffFormatStrategy(base=base_args)


class _BlackStrategy(CommandBuilder):
    """Command builder providing Black formatter behaviour."""

    base: tuple[str, ...]
    mode: str

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        line_length = _setting(settings, "line-length")
        if line_length is not None:
            cmd.extend(["--line-length", str(line_length)])

        target_versions = _settings_list(_setting(settings, "target-version"))
        if target_versions:
            for version in target_versions:
                cmd.extend(["--target-version", str(version)])
        else:
            cmd.extend(["--target-version", _python_version_tag(_python_target_version(ctx))])

        if _as_bool(_setting(settings, "preview")):
            cmd.append("--preview")

        if _as_bool(_setting(settings, "skip-string-normalization")):
            cmd.append("--skip-string-normalization")

        if _as_bool(_setting(settings, "skip-magic-trailing-comma")):
            cmd.append("--skip-magic-trailing-comma")

        workers = _setting(settings, "workers")
        if workers is not None:
            cmd.extend(["-j", str(workers)])

        additional_args = _settings_list(_setting(settings, "args"))
        if additional_args:
            cmd.extend(str(arg) for arg in additional_args)

        return tuple(cmd)


def black_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for Black."""

    base_args = _require_string_sequence(config, "base", context="command_black")
    mode_value = _require_str(config, "mode", context="command_black")
    return _BlackStrategy(base=base_args, mode=mode_value)


class _IsortStrategy(CommandBuilder):
    """Command builder that wraps isort CLI arguments."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        settings_path = _setting(settings, "settings-path", "config")
        if settings_path:
            cmd.extend(["--settings-path", str(_resolve_path(root, settings_path))])

        profile = _setting(settings, "profile")
        if profile:
            cmd.extend(["--profile", str(profile)])
        else:
            cmd.extend(["--profile", "black"])

        line_length = _setting(settings, "line-length")
        if line_length is None:
            line_length = ctx.cfg.execution.line_length
        if line_length is not None:
            cmd.extend(["--line-length", str(line_length)])

        py_version = _setting(settings, "py", "python-version")
        if py_version is not None:
            cmd.extend(["--py", str(py_version)])
        else:
            cmd.extend(["--py", _python_version_number(_python_target_version(ctx))])

        for option in ("multi-line", "indent", "wrap-length"):
            value = _setting(settings, option, option.replace("-", "_"))
            if value is not None:
                cmd.extend([f"--{option}", str(value)])

        src_paths = _settings_list(_setting(settings, "src"))
        for path in src_paths:
            cmd.extend(["--src", str(_resolve_path(root, path))])

        for key in ("virtual-env", "conda-env"):
            value = _setting(settings, key, key.replace("-", "_"))
            if value:
                cmd.extend([f"--{key}", str(_resolve_path(root, value))])

        for skip in _settings_list(_setting(settings, "skip")):
            cmd.extend(["--skip", str(skip)])

        for skip in _settings_list(_setting(settings, "extend-skip", "extend_skip")):
            cmd.extend(["--extend-skip", str(skip)])

        for pattern in _settings_list(_setting(settings, "skip-glob", "skip_glob")):
            cmd.extend(["--skip-glob", str(pattern)])

        for pattern in _settings_list(_setting(settings, "extend-skip-glob", "extend_skip_glob")):
            cmd.extend(["--extend-skip-glob", str(pattern)])

        if _as_bool(_setting(settings, "filter-files", "filter_files")):
            cmd.append("--filter-files")

        if _as_bool(_setting(settings, "float-to-top", "float_to_top")):
            cmd.append("--float-to-top")

        if _as_bool(_setting(settings, "combine-as", "combine_as")):
            cmd.append("--combine-as")

        if _as_bool(_setting(settings, "combine-star", "combine_star")):
            cmd.append("--combine-star")

        color = _as_bool(_setting(settings, "color"))
        if color is True:
            cmd.append("--color")
        elif color is False:
            cmd.append("--no-color")

        additional_args = _settings_list(_setting(settings, "args"))
        if additional_args:
            cmd.extend(str(arg) for arg in additional_args)

        return tuple(cmd)


def isort_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for isort."""

    base_args = _require_string_sequence(config, "base", context="command_isort")
    return _IsortStrategy(base=base_args)


class _MypyStrategy(CommandBuilder):
    """Command builder replicating mypy CLI behaviour."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config_file = _setting(settings, "config", "config-file")
        if config_file:
            cmd.extend(["--config-file", str(_resolve_path(root, config_file))])

        flag_map = {
            "exclude-gitignore": "--exclude-gitignore",
            "sqlite-cache": "--sqlite-cache",
            "strict": "--strict",
            "ignore-missing-imports": "--ignore-missing-imports",
            "namespace-packages": "--namespace-packages",
            "warn-unused-configs": "--warn-unused-configs",
            "warn-return-any": "--warn-return-any",
            "warn-redundant-casts": "--warn-redundant-casts",
            "warn-unused-ignores": "--warn-unused-ignores",
            "warn-unreachable": "--warn-unreachable",
            "disallow-untyped-decorators": "--disallow-untyped-decorators",
            "disallow-any-generics": "--disallow-any-generics",
            "check-untyped-defs": "--check-untyped-defs",
            "no-implicit-reexport": "--no-implicit-reexport",
            "show-error-codes": "--show-error-codes",
            "show-column-numbers": "--show-column-numbers",
        }
        for setting_name, flag in flag_map.items():
            if _as_bool(_setting(settings, setting_name, setting_name.replace("-", "_"))):
                cmd.append(flag)

        python_version = _setting(settings, "python-version", "python_version")
        if not python_version:
            python_version = _python_target_version(ctx)
        if python_version:
            cmd.extend(["--python-version", str(python_version)])

        python_exec = _setting(settings, "python-executable", "python_executable")
        if python_exec:
            cmd.extend(["--python-executable", str(_resolve_path(root, python_exec))])

        plugins = _settings_list(_setting(settings, "plugins"))
        for plugin in plugins:
            cmd.extend(["--plugin", str(plugin)])

        cache_dir = _setting(settings, "cache-dir", "cache_dir")
        if cache_dir:
            cmd.extend(["--cache-dir", str(_resolve_path(root, cache_dir))])

        additional_args = _settings_list(_setting(settings, "args"))
        if additional_args:
            cmd.extend(str(arg) for arg in additional_args)

        return tuple(cmd)


def mypy_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for mypy."""

    base_args = _require_string_sequence(config, "base", context="command_mypy")
    return _MypyStrategy(base=base_args)


class _PylintStrategy(CommandBuilder):
    """Command builder mirroring pylint CLI behaviour."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        rcfile = _setting(settings, "rcfile", "config")
        if rcfile:
            cmd.extend(["--rcfile", str(_resolve_path(root, rcfile))])

        explicit_plugins = _settings_list(_setting(settings, "load-plugins", "plugins"))
        if explicit_plugins:
            for plugin in explicit_plugins:
                cmd.extend(["--load-plugins", str(plugin)])
        else:
            plugins = _discover_pylint_plugins(root)
            if plugins:
                cmd.extend(["--load-plugins", ",".join(plugins)])

        disable = _settings_list(_setting(settings, "disable"))
        if disable:
            cmd.extend(["--disable", ",".join(disable)])

        enable = _settings_list(_setting(settings, "enable"))
        if enable:
            cmd.extend(["--enable", ",".join(enable)])

        jobs = _setting(settings, "jobs")
        if jobs is not None:
            cmd.extend(["-j", str(jobs)])

        fail_under = _setting(settings, "fail-under", "fail_under")
        if fail_under is not None:
            cmd.extend(["--fail-under", str(fail_under)])

        if _as_bool(_setting(settings, "exit-zero", "exit_zero")):
            cmd.append("--exit-zero")

        score = _setting(settings, "score")
        if score is not None:
            cmd.append(f"--score={'y' if _as_bool(score) else 'n'}")

        reports = _setting(settings, "reports")
        if reports is not None:
            cmd.append(f"--reports={'y' if _as_bool(reports) else 'n'}")

        line_length = _setting(settings, "max-line-length", "max_line_length")
        if line_length is None:
            line_length = ctx.cfg.execution.line_length
        if line_length is not None:
            cmd.extend(["--max-line-length", str(line_length)])

        complexity = _setting(settings, "max-complexity", "max_complexity")
        if complexity is None:
            complexity = ctx.cfg.complexity.max_complexity
        if complexity is not None:
            cmd.extend(["--max-complexity", str(complexity)])

        max_args = _setting(settings, "max-args", "max_args")
        if max_args is None:
            max_args = ctx.cfg.complexity.max_arguments
        if max_args is not None:
            cmd.extend(["--max-args", str(max_args)])

        max_pos_args = _setting(settings, "max-positional-arguments", "max_positional_arguments")
        if max_pos_args is None:
            max_pos_args = ctx.cfg.complexity.max_arguments
        if max_pos_args is not None:
            cmd.extend(["--max-positional-arguments", str(max_pos_args)])

        init_import = _setting(settings, "init-import", "init_import")
        if init_import is not None:
            cmd.append(f"--init-import={'y' if _as_bool(init_import) else 'n'}")

        py_version = _setting(settings, "py-version", "py_version")
        if py_version is None:
            py_version = _python_target_version(ctx)
        if py_version:
            cmd.extend(["--py-version", str(py_version)])

        additional_args = _settings_list(_setting(settings, "args"))
        if additional_args:
            cmd.extend(str(arg) for arg in additional_args)

        return tuple(cmd)


def pylint_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for pylint."""

    base_args = _require_string_sequence(config, "base", context="command_pylint")
    return _PylintStrategy(base=base_args)


class _PyrightStrategy(CommandBuilder):
    """Command builder replicating pyright CLI behaviour."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        project = _setting(settings, "project", "config")
        if project:
            cmd.extend(["--project", str(_resolve_path(root, project))])

        venv_path = _setting(settings, "venv-path", "venv_path")
        if venv_path:
            cmd.extend(["--venv-path", str(_resolve_path(root, venv_path))])

        pythonpath = _setting(settings, "pythonpath")
        if pythonpath:
            cmd.extend(["--pythonpath", str(_resolve_path(root, pythonpath))])

        typeshed_path = _setting(settings, "typeshed-path", "typeshed_path")
        if typeshed_path:
            cmd.extend(["--typeshed-path", str(_resolve_path(root, typeshed_path))])

        python_platform = _setting(settings, "python-platform", "python_platform")
        if python_platform:
            cmd.extend(["--pythonplatform", str(python_platform)])

        python_version = _setting(settings, "python-version", "python_version")
        if not python_version:
            python_version = _python_target_version(ctx)
        if python_version:
            cmd.extend(["--pythonversion", str(python_version)])

        if _as_bool(_setting(settings, "lib")):
            cmd.append("--lib")

        verifytypes = _setting(settings, "verifytypes")
        if verifytypes:
            cmd.extend(["--verifytypes", str(verifytypes)])

        if _as_bool(_setting(settings, "ignoreexternal", "ignore-external")):
            cmd.append("--ignoreexternal")

        additional_args = _settings_list(_setting(settings, "args"))
        if additional_args:
            cmd.extend(str(arg) for arg in additional_args)

        return tuple(cmd)


def pyright_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for pyright."""

    base_args = _require_string_sequence(config, "base", context="command_pyright")
    return _PyrightStrategy(base=base_args)


class _SqlfluffStrategy(CommandBuilder):
    """Command builder modelling sqlfluff lint/fix behaviour."""

    base: tuple[str, ...]
    is_fix: bool = False

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config_path = _setting(settings, "config", "config_path")
        if config_path:
            cmd.extend(["--config", str(_resolve_path(root, config_path))])

        dialect = _setting(settings, "dialect") or getattr(ctx.cfg.execution, "sql_dialect", None)
        if dialect:
            cmd.extend(["--dialect", str(dialect)])

        templater = _setting(settings, "templater")
        if templater:
            cmd.extend(["--templater", str(templater)])

        for rule in _settings_list(_setting(settings, "rules")):
            cmd.extend(["--rules", str(rule)])

        processes = _setting(settings, "processes")
        if processes is not None:
            cmd.extend(["--processes", str(processes)])

        additional_args = _settings_list(_setting(settings, "args"))
        if additional_args:
            cmd.extend(str(arg) for arg in additional_args)

        return tuple(cmd)


def sqlfluff_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for sqlfluff."""

    base_args = _require_string_sequence(config, "base", context="command_sqlfluff")
    is_fix_value = _as_bool(config.get("isFix")) if config.get("isFix") is not None else False
    return _SqlfluffStrategy(base=base_args, is_fix=is_fix_value)


class _PyupgradeStrategy(CommandBuilder):
    """Command builder that applies pyupgrade-specific arguments."""

    base: tuple[str, ...]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        settings = ctx.settings

        pyplus_value = _setting(settings, "pyplus", "py_plus", "py_version")
        if pyplus_value:
            flag = str(pyplus_value).strip()
            if not flag.startswith("--"):
                flag = _pyupgrade_flag_from_version(flag)
            cmd.append(flag)
        else:
            cmd.append(_pyupgrade_flag_from_version(_python_target_version(ctx)))

        bool_flags = {
            "keep-mock": "--keep-mock",
            "keep-runtime-typing": "--keep-runtime-typing",
            "keep-percent-format": "--keep-percent-format",
            "keep-annotations": "--keep-annotations",
            "keep-logging-format": "--keep-logging-format",
            "exit-zero-even-if-changed": "--exit-zero-even-if-changed",
            "no-verify": "--no-verify",
        }

        for key, flag in bool_flags.items():
            if _as_bool(_setting(settings, key, key.replace("-", "_"))):
                cmd.append(flag)

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


def pyupgrade_command(config: Mapping[str, Any]) -> CommandBuilder:
    """Return a command builder configured for pyupgrade."""

    base_config = config.get("base")
    if base_config is None:
        base_args = ("pyupgrade",)
    else:
        base_tuple = _normalize_sequence(base_config)
        if not base_tuple:
            raise CatalogIntegrityError("pyupgrade_command: 'base' must contain at least one argument")
        base_args = tuple(str(part) for part in base_tuple)
    return _PyupgradeStrategy(base=base_args)


__all__ = [
    "black_command",
    "isort_command",
    "mypy_command",
    "pyright_command",
    "pylint_command",
    "pyupgrade_command",
    "ruff_command",
    "ruff_format_command",
    "sqlfluff_command",
]
