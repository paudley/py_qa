# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
# SPDX-License-Identifier: MIT
"""Command builder implementations for built-in tools."""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .base import CommandBuilder, ToolContext
from .builtin_helpers import _as_bool, _resolve_path, _setting, _settings_list

_BASE_PYLINT_PLUGINS: tuple[str, ...] = (
    "pylint.extensions.bad_builtin",
    "pylint.extensions.broad_try_clause",
    "pylint.extensions.check_elif",
    "pylint.extensions.code_style",
    "pylint.extensions.comparison_placement",
    "pylint.extensions.confusing_elif",
    "pylint.extensions.consider_ternary_expression",
    "pylint.extensions.dict_init_mutate",
    "pylint.extensions.docparams",
    "pylint.extensions.docstyle",
    "pylint.extensions.empty_comment",
    "pylint.extensions.eq_without_hash",
    "pylint.extensions.for_any_all",
    "pylint.extensions.magic_value",
    "pylint.extensions.mccabe",
    "pylint.extensions.overlapping_exceptions",
    "pylint.extensions.redefined_loop_name",
    "pylint.extensions.redefined_variable_type",
    "pylint.extensions.set_membership",
    "pylint.extensions.typing",
    "pylint.extensions.while_used",
    "pylint_htmf",
    "pylint_pydantic",
)

_OPTIONAL_PYLINT_PLUGINS: dict[str, str] = {
    "django": "pylint_django",
    "celery": "pylint_celery",
    "flask": "pylint_flask",
    "pytest": "pylint_pytest",
    "sqlalchemy": "pylint_sqlalchemy",
    "odoo": "pylint_odoo",
    "quotes": "pylint_quotes",
}


def _python_target_version(ctx: ToolContext) -> str:
    version = getattr(ctx.cfg.execution, "python_version", None)
    if version:
        return str(version)
    info = sys.version_info
    return f"{info.major}.{info.minor}"


def _python_version_components(version: str) -> tuple[int, int]:
    match = re.search(r"(\d{1,2})(?:[._-]?(\d{1,2}))?", version)
    if not match:
        return sys.version_info.major, sys.version_info.minor
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) is not None else 0
    return major, minor


def _python_version_tag(version: str) -> str:
    major, minor = _python_version_components(version)
    return f"py{major}{minor}"


def _python_version_number(version: str) -> str:
    major, minor = _python_version_components(version)
    return f"{major}{minor}"


def _pyupgrade_flag_from_version(version: str) -> str:
    normalized = version.lower().lstrip("py").rstrip("+")
    if not normalized:
        normalized = f"{sys.version_info.major}.{sys.version_info.minor}"
    parts = normalized.split(".")
    if len(parts) > 1:
        major, minor = parts[0], parts[1]
    else:
        major = parts[0][:1] if parts[0] else str(sys.version_info.major)
        minor = parts[0][1:] if len(parts[0]) > 1 else "0"
        if not minor:
            minor = "0"
    return f"--py{major}{minor}-plus"


def _discover_pylint_plugins(root: Path) -> tuple[str, ...]:
    """Return the set of pylint plugins that should be enabled by default."""
    discovered: set[str] = set()

    def _loadable(module: str) -> bool:
        try:
            spec = importlib.util.find_spec(module)
            if spec is None:
                return False
            mod = importlib.import_module(module)
            return hasattr(mod, "register")
        except Exception:
            return False

    for plugin in _BASE_PYLINT_PLUGINS:
        if _loadable(plugin):
            discovered.add(plugin)

    for requirement, plugin in _OPTIONAL_PYLINT_PLUGINS.items():
        if _loadable(requirement) and _loadable(plugin):
            discovered.add(plugin)

    if (root / ".venv").is_dir() and _loadable("pylint_venv"):
        discovered.add("pylint_venv")

    return tuple(sorted(discovered))


@dataclass(slots=True)
class _RuffCommand(CommandBuilder):
    base: Sequence[str]
    mode: str  # "lint" or "fix"

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config = _setting(settings, "config")
        if config:
            cmd.extend(["--config", str(_resolve_path(root, config))])

        select = _settings_list(_setting(settings, "select"))
        if select:
            cmd.extend(["--select", ",".join(select)])

        ignore = _settings_list(_setting(settings, "ignore"))
        if ignore:
            cmd.extend(["--ignore", ",".join(ignore)])

        extend_select = _settings_list(_setting(settings, "extend-select"))
        if extend_select:
            cmd.extend(["--extend-select", ",".join(extend_select)])

        extend_ignore = _settings_list(_setting(settings, "extend-ignore"))
        if extend_ignore:
            cmd.extend(["--extend-ignore", ",".join(extend_ignore)])

        line_length = _setting(settings, "line-length")
        if line_length is None:
            line_length = ctx.cfg.execution.line_length
        if line_length is not None:
            cmd.extend(["--line-length", str(line_length)])

        target_version = _setting(settings, "target-version")
        if target_version:
            cmd.extend(["--target-version", str(target_version)])
        else:
            cmd.extend(
                [
                    "--target-version",
                    _python_version_tag(_python_target_version(ctx)),
                ],
            )

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


@dataclass(slots=True)
class _RuffFormatCommand(CommandBuilder):
    base: Sequence[str]

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
            cmd.extend(
                [
                    "--target-version",
                    _python_version_tag(_python_target_version(ctx)),
                ],
            )

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

        stdin_filename = _setting(settings, "stdin-filename")
        if stdin_filename:
            cmd.extend(["--stdin-filename", str(stdin_filename)])

        additional_args = _settings_list(_setting(settings, "args"))
        if additional_args:
            cmd.extend(str(arg) for arg in additional_args)

        return tuple(cmd)


@dataclass(slots=True)
class _IsortCommand(CommandBuilder):
    base: Sequence[str]

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

        multi_line = _setting(settings, "multi-line", "multi_line")
        if multi_line:
            cmd.extend(["--multi-line", str(multi_line)])

        src_paths = _settings_list(_setting(settings, "src"))
        for path in src_paths:
            cmd.extend(["--src", str(_resolve_path(root, path))])

        virtual_env = _setting(settings, "virtual-env", "virtual_env")
        if virtual_env:
            cmd.extend(["--virtual-env", str(_resolve_path(root, virtual_env))])

        conda_env = _setting(settings, "conda-env", "conda_env")
        if conda_env:
            cmd.extend(["--conda-env", str(_resolve_path(root, conda_env))])

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


@dataclass(slots=True)
class _BlackCommand(CommandBuilder):
    base: Sequence[str]
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
        for version in target_versions:
            cmd.extend(["--target-version", str(version)])
        if not target_versions:
            cmd.extend(
                [
                    "--target-version",
                    _python_version_tag(_python_target_version(ctx)),
                ],
            )

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


@dataclass(slots=True)
class _CpplintCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        line_length = _setting(settings, "linelength", "line-length")
        if line_length is None:
            line_length = ctx.cfg.execution.line_length
        if line_length is not None:
            cmd.append(f"--linelength={line_length}")

        for filt in _settings_list(_setting(settings, "filter")):
            cmd.append(f"--filter={filt}")

        for exclude in _settings_list(_setting(settings, "exclude")):
            cmd.append(f"--exclude={_resolve_path(root, exclude)}")

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

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


__all__ = [
    "_BlackCommand",
    "_CpplintCommand",
    "_IsortCommand",
    "_RuffCommand",
    "_RuffFormatCommand",
]
