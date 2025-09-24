# SPDX-License-Identifier: MIT
"""Command builder implementations for built-in tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .base import CommandBuilder, ToolContext
from .builtin_helpers import _as_bool, _resolve_path, _setting, _settings_list


@dataclass(slots=True)
class _BanditCommand(CommandBuilder):
    """Command builder that injects excludes and discovery roots for Bandit."""

    base_args: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        settings = dict(ctx.settings)
        cmd = list(self.base_args)
        root = ctx.root

        exclude_paths: set[Path] = set()
        exclude_args: set[str] = set()
        for entry in _settings_list(settings.pop("exclude", None)):
            candidate = _resolve_path(root, entry)
            exclude_paths.add(candidate)
            try:
                exclude_args.add(str(candidate.relative_to(root)))
                exclude_args.add(str(candidate))
            except ValueError:
                exclude_args.add(str(candidate))
        for path in ctx.cfg.file_discovery.excludes:
            resolved = path if path.is_absolute() else root / path
            exclude_paths.add(resolved)
            try:
                exclude_args.add(str(resolved.relative_to(root)))
                exclude_args.add(str(resolved))
            except ValueError:
                exclude_args.add(str(resolved))
        if exclude_args:
            cmd.extend(["-x", ",".join(sorted(exclude_args))])

        target_dirs: set[Path] = set()
        for extra_target in _settings_list(settings.pop("targets", None)):
            target_dirs.add(_resolve_path(root, extra_target))
        for directory in ctx.cfg.file_discovery.roots:
            resolved = directory if directory.is_absolute() else root / directory
            if resolved == root:
                continue
            if self._is_under(resolved, exclude_paths):
                continue
            target_dirs.add(resolved)

        for file_path in ctx.cfg.file_discovery.explicit_files:
            resolved_file = file_path if file_path.is_absolute() else root / file_path
            parent = resolved_file.parent
            if not self._is_under(parent, exclude_paths):
                target_dirs.add(parent)

        if not target_dirs:
            src_dir = root / "src"
            if src_dir.exists() and not self._is_under(src_dir, exclude_paths):
                target_dirs.add(src_dir)
            else:
                target_dirs.add(root)

        normalized_targets = sorted(str(path) for path in target_dirs)
        cmd.append("-r")
        cmd.extend(normalized_targets)

        config_path = _setting(settings, "config", "configfile")
        if config_path:
            cmd.extend(["-c", str(_resolve_path(root, config_path))])

        baseline = _setting(settings, "baseline")
        if baseline:
            cmd.extend(["--baseline", str(_resolve_path(root, baseline))])

        report_fmt = _setting(settings, "format")
        if report_fmt:
            cmd.extend(["--format", str(report_fmt)])

        severity = _setting(settings, "severity", "severity_level")
        if severity:
            cmd.extend(["--severity-level", str(severity)])

        confidence = _setting(settings, "confidence", "confidence_level")
        if confidence:
            cmd.extend(["--confidence-level", str(confidence)])

        skip_tests = _settings_list(_setting(settings, "skip", "skips"))
        if skip_tests:
            cmd.extend(["--skip", ",".join(skip_tests)])

        additional_args = _settings_list(_setting(settings, "args"))
        if additional_args:
            cmd.extend(str(arg) for arg in additional_args)

        return tuple(cmd)

    @staticmethod
    def _is_under(candidate: Path, excluded: set[Path]) -> bool:
        for base in excluded:
            try:
                candidate.relative_to(base)
                return True
            except ValueError:
                continue
        return False


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
        else:
            if _as_bool(_setting(settings, "fix")) is False:
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

        line_length = _setting(settings, "line-length")
        if line_length is None:
            line_length = ctx.cfg.execution.line_length
        if line_length is not None:
            cmd.extend(["--line-length", str(line_length)])

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

        for pattern in _settings_list(
            _setting(settings, "extend-skip-glob", "extend_skip_glob")
        ):
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
class _MypyCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config_file = _setting(settings, "config", "config-file")
        if config_file:
            cmd.extend(["--config-file", str(_resolve_path(root, config_file))])

        if _as_bool(_setting(settings, "strict")):
            cmd.append("--strict")

        if _as_bool(_setting(settings, "ignore-missing-imports")):
            cmd.append("--ignore-missing-imports")

        if _as_bool(_setting(settings, "namespace-packages")):
            cmd.append("--namespace-packages")

        if _as_bool(_setting(settings, "warn-unused-configs")):
            cmd.append("--warn-unused-configs")

        if _as_bool(_setting(settings, "warn-return-any")):
            cmd.append("--warn-return-any")

        python_version = _setting(settings, "python-version")
        if python_version:
            cmd.extend(["--python-version", str(python_version)])

        python_exec = _setting(settings, "python-executable")
        if python_exec:
            cmd.extend(["--python-executable", str(_resolve_path(root, python_exec))])

        plugins = _settings_list(_setting(settings, "plugins"))
        for plugin in plugins:
            cmd.extend(["--plugin", str(plugin)])

        cache_dir = _setting(settings, "cache-dir")
        if cache_dir:
            cmd.extend(["--cache-dir", str(_resolve_path(root, cache_dir))])

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


@dataclass(slots=True)
class _PylintCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        rcfile = _setting(settings, "rcfile", "config")
        if rcfile:
            cmd.extend(["--rcfile", str(_resolve_path(root, rcfile))])

        for plugin in _settings_list(_setting(settings, "load-plugins", "plugins")):
            cmd.extend(["--load-plugins", str(plugin)])

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

        exit_zero = _as_bool(_setting(settings, "exit-zero", "exit_zero"))
        if exit_zero:
            cmd.append("--exit-zero")

        score = _as_bool(_setting(settings, "score"))
        if score is True:
            cmd.append("--score=y")
        elif score is False:
            cmd.append("--score=n")

        reports = _as_bool(_setting(settings, "reports"))
        if reports is True:
            cmd.append("--reports=y")
        elif reports is False:
            cmd.append("--reports=n")

        max_line_length = _setting(settings, "max-line-length", "max_line_length")
        if max_line_length is None:
            max_line_length = ctx.cfg.execution.line_length
        if max_line_length is not None:
            cmd.extend(["--max-line-length", str(max_line_length)])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _PyrightCommand(CommandBuilder):
    base: Sequence[str]

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
        if python_version:
            cmd.extend(["--pythonversion", str(python_version)])

        if _as_bool(_setting(settings, "lib")):
            cmd.append("--lib")

        verifytypes = _setting(settings, "verifytypes")
        if verifytypes:
            cmd.extend(["--verifytypes", str(verifytypes)])

        if _as_bool(_setting(settings, "ignoreexternal", "ignore-external")):
            cmd.append("--ignoreexternal")

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _SqlfluffCommand(CommandBuilder):
    base: Sequence[str]
    is_fix: bool = False

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        config_path = _setting(settings, "config", "config_path")
        if config_path:
            cmd.extend(["--config", str(_resolve_path(root, config_path))])

        dialect = _setting(settings, "dialect") or ctx.cfg.execution.sql_dialect
        if dialect:
            cmd.extend(["--dialect", str(dialect)])

        templater = _setting(settings, "templater")
        if templater:
            cmd.extend(["--templater", str(templater)])

        rules = _settings_list(_setting(settings, "rules"))
        for rule in rules:
            cmd.extend(["--rules", str(rule)])

        processes = _setting(settings, "processes")
        if processes is not None:
            cmd.extend(["--processes", str(processes)])

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


@dataclass(slots=True)
class _TombiCommand(CommandBuilder):
    base: Sequence[str]

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cmd = list(self.base)
        root = ctx.root
        settings = ctx.settings

        stdin_filename = _setting(settings, "stdin-filename", "stdin_filename")
        if stdin_filename:
            value = str(stdin_filename)
            if value == "-":
                cmd.extend(["--stdin-filename", value])
            else:
                cmd.extend(
                    ["--stdin-filename", str(_resolve_path(root, stdin_filename))]
                )

        if _as_bool(_setting(settings, "offline")):
            cmd.append("--offline")

        if _as_bool(_setting(settings, "no-cache", "no_cache")):
            cmd.append("--no-cache")

        verbose = _setting(settings, "verbose")
        if isinstance(verbose, int):
            cmd.extend(["-v"] * max(verbose, 0))
        elif _as_bool(verbose):
            cmd.append("-v")

        quiet = _setting(settings, "quiet")
        if isinstance(quiet, int):
            cmd.extend(["-q"] * max(quiet, 0))
        elif _as_bool(quiet):
            cmd.append("-q")

        args = _settings_list(_setting(settings, "args"))
        if args:
            cmd.extend(str(arg) for arg in args)

        return tuple(cmd)


__all__ = [
    "_BanditCommand",
    "_RuffCommand",
    "_RuffFormatCommand",
    "_IsortCommand",
    "_BlackCommand",
    "_MypyCommand",
    "_PylintCommand",
    "_PyrightCommand",
    "_SqlfluffCommand",
    "_TombiCommand",
    "_CpplintCommand",
]
