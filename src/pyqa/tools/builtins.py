# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Registration helpers for the built-in tool suite."""

from __future__ import annotations

import io
import os
import platform
import stat
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import requests

from ..models import RawDiagnostic
from ..parsers import (
    JsonParser,
    TextParser,
    parse_bandit,
    parse_cargo_clippy,
    parse_eslint,
    parse_stylelint,
    parse_golangci_lint,
    parse_actionlint,
    parse_kube_linter,
    parse_sqlfluff,
    parse_mypy,
    parse_pylint,
    parse_pyright,
    parse_ruff,
    parse_tsc,
)
from ..severity import Severity
from .base import CommandBuilder, DeferredCommand, Tool, ToolAction, ToolContext
from .registry import DEFAULT_REGISTRY, ToolRegistry


def _setting(settings: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in settings:
            return settings[name]
        alt = name.replace("-", "_")
        if alt in settings:
            return settings[alt]
    return None


def _settings_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]


def _resolve_path(root: Path, value: Any) -> Path:
    candidate = Path(str(value)).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


ACTIONLINT_VERSION_DEFAULT = "1.7.1"


def _ensure_actionlint(version: str, cache_root: Path) -> Path:
    base_dir = cache_root / "actionlint" / version
    binary = base_dir / "actionlint"
    if binary.exists():
        return binary

    base_dir.mkdir(parents=True, exist_ok=True)

    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        if machine in {"x86_64", "amd64"}:
            platform_tag = "linux_amd64"
        elif machine in {"aarch64", "arm64"}:
            platform_tag = "linux_arm64"
        else:
            raise RuntimeError(f"Unsupported Linux architecture '{machine}' for actionlint")
    elif system == "darwin":
        if machine in {"x86_64", "amd64"}:
            platform_tag = "darwin_amd64"
        elif machine in {"arm64", "aarch64"}:
            platform_tag = "darwin_arm64"
        else:
            raise RuntimeError(f"Unsupported macOS architecture '{machine}' for actionlint")
    else:
        raise RuntimeError(f"actionlint is not supported on platform '{system}'")

    filename = f"actionlint_{version}_{platform_tag}.tar.gz"
    url = f"https://github.com/rhysd/actionlint/releases/download/v{version}/{filename}"

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(response.content)
        tmp.flush()
        with tarfile.open(tmp.name, "r:gz") as archive:
            for member in archive.getmembers():
                if member.isfile() and member.name.endswith("actionlint"):
                    archive.extract(member, path=base_dir)
                    extracted = base_dir / member.name
                    extracted.chmod(extracted.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    if extracted != binary:
                        extracted.rename(binary)
                    break
            else:
                raise RuntimeError("Failed to locate actionlint binary in archive")

    return binary


def _parse_gofmt_check(stdout: str, _context: ToolContext) -> list[RawDiagnostic]:
    diagnostics: list[RawDiagnostic] = []
    for line in stdout.splitlines():
        path = line.strip()
        if not path:
            continue
        diagnostics.append(
            RawDiagnostic(
                file=path,
                line=None,
                column=None,
                severity=Severity.WARNING,
                message="File requires gofmt formatting",
                code="gofmt",
                tool="gofmt",
            )
        )
    return diagnostics


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
            except ValueError:
                exclude_args.add(str(candidate))
        for path in ctx.cfg.file_discovery.excludes:
            resolved = path if path.is_absolute() else root / path
            exclude_paths.add(resolved)
            try:
                exclude_args.add(str(resolved.relative_to(root)))
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

        resolve_plugins = _setting(settings, "resolve-plugins-relative-to", "resolve_plugins_relative_to")
        if resolve_plugins:
            cmd.extend(
                [
                    "--resolve-plugins-relative-to",
                    str(_resolve_path(root, resolve_plugins)),
                ]
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
            )
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
                ]
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

        for directory in _settings_list(_setting(settings, "plugin-search-dir", "plugin_search_dir")):
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
class _ActionlintCommand(CommandBuilder):
    version: str

    def build(self, ctx: ToolContext) -> Sequence[str]:
        cache_root = ctx.root / ".lint-cache"
        binary = _ensure_actionlint(self.version, cache_root)
        cmd = [str(binary), "--format", "json", "--color", "never"]
        workflows = ctx.root / ".github" / "workflows"
        if workflows.exists():
            cmd.append(str(workflows))
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


def register_builtin_tools(registry: ToolRegistry | None = None) -> None:
    registry = registry or DEFAULT_REGISTRY
    for tool in _builtin_tools():
        registry.register(tool)


def _builtin_tools() -> Iterable[Tool]:
    yield Tool(
        name="ruff",
        actions=(
            ToolAction(
                name="lint",
                command=_RuffCommand(
                    base=(
                        "ruff",
                        "check",
                        "--force-exclude",
                        "--output-format",
                        "json",
                    ),
                    mode="lint",
                ),
                append_files=True,
                description="Run ruff against the discovered Python files.",
                parser=JsonParser(parse_ruff),
            ),
            ToolAction(
                name="fix",
                command=_RuffCommand(
                    base=("ruff", "check", "--fix", "--force-exclude"),
                    mode="fix",
                ),
                append_files=True,
                is_fix=True,
                description="Run ruff autofix.",
            ),
        ),
        languages=("python",),
        file_extensions=(".py", ".pyi"),
        config_files=("pyproject.toml", "ruff.toml"),
        description="Python linter powered by Ruff.",
        runtime="python",
        package="ruff",
        min_version="0.6.8",
        version_command=("ruff", "--version"),
    )

    yield Tool(
        name="black",
        actions=(
            ToolAction(
                name="format",
                command=_BlackCommand(base=("black",), mode="format"),
                append_files=True,
                is_fix=True,
                description="Format Python sources using Black.",
            ),
            ToolAction(
                name="check",
                command=_BlackCommand(base=("black", "--check"), mode="check"),
                append_files=True,
                description="Check code style without modification.",
            ),
        ),
        languages=("python",),
        file_extensions=(".py", ".pyi"),
        config_files=("pyproject.toml", "black.toml"),
        description="Python formatter Black.",
        runtime="python",
        package="black",
        min_version="25.1.0",
        version_command=("black", "--version"),
    )

    yield Tool(
        name="mypy",
        actions=(
            ToolAction(
                name="type-check",
                command=_MypyCommand(base=("mypy", "--output", "json")),
                append_files=True,
                description="Run mypy type checker.",
                parser=JsonParser(parse_mypy),
            ),
        ),
        languages=("python",),
        file_extensions=(".py", ".pyi"),
        config_files=("pyproject.toml", "mypy.ini", "setup.cfg"),
        description="Python static type checking with mypy.",
        runtime="python",
        package="mypy",
        min_version="1.18.1",
        version_command=("mypy", "--version"),
    )

    yield Tool(
        name="ruff-format",
        actions=(
            ToolAction(
                name="format",
                command=_RuffFormatCommand(base=("ruff", "format", "--force-exclude")),
                append_files=True,
                is_fix=True,
                description="Format files using Ruff formatter.",
            ),
        ),
        languages=("python",),
        file_extensions=(".py", ".pyi"),
        description="Code formatter provided by Ruff.",
        runtime="python",
        package="ruff",
        min_version="0.6.8",
        version_command=("ruff", "--version"),
    )

    yield Tool(
        name="isort",
        actions=(
            ToolAction(
                name="sort",
                command=_IsortCommand(base=("isort",)),
                append_files=True,
                is_fix=True,
                description="Apply import sorting with isort.",
            ),
            ToolAction(
                name="check",
                command=_IsortCommand(base=("isort", "--check-only")),
                append_files=True,
                description="Check import ordering without writing changes.",
            ),
        ),
        languages=("python",),
        file_extensions=(".py",),
        description="Import sorter for Python projects.",
        runtime="python",
        package="isort",
        min_version="6.0.1",
        version_command=("isort", "--version"),
    )

    yield Tool(
        name="pylint",
        actions=(
            ToolAction(
                name="lint",
                command=_PylintCommand(base=("pylint", "--output-format=json")),
                append_files=True,
                description="Static analysis with pylint.",
                parser=JsonParser(parse_pylint),
            ),
        ),
        languages=("python",),
        file_extensions=(".py",),
        description="Python linter providing detailed diagnostics.",
        runtime="python",
        package="pylint",
        min_version="3.3.8",
        version_command=("pylint", "--version"),
    )

    yield Tool(
        name="pyright",
        actions=(
            ToolAction(
                name="type-check",
                command=_PyrightCommand(base=("pyright", "--outputjson")),
                append_files=True,
                description="Type checking using Microsoft's Pyright.",
                parser=JsonParser(parse_pyright),
            ),
        ),
        languages=("python",),
        file_extensions=(".py", ".pyi"),
        description="Optional Python type checker for projects targeting Pyright.",
        runtime="python",
        package="pyright",
        min_version="1.1.405",
        version_command=("pyright", "--version"),
    )

    yield Tool(
        name="bandit",
        actions=(
            ToolAction(
                name="security",
                command=_BanditCommand(["bandit", "-q", "-f", "json"]),
                append_files=False,
                description="Bandit security analysis for Python code.",
                parser=JsonParser(parse_bandit),
            ),
        ),
        languages=("python",),
        file_extensions=(".py",),
        description="Python security linting via Bandit.",
        runtime="python",
        package="bandit[baseline,sarif,toml]",
        min_version="1.8.6",
        version_command=("bandit", "--version"),
    )

    yield Tool(
        name="mdformat",
        actions=(
            ToolAction(
                name="format",
                command=DeferredCommand(["mdformat"]),
                append_files=True,
                is_fix=True,
                description="Format Markdown files using mdformat.",
            ),
            ToolAction(
                name="check",
                command=DeferredCommand(["mdformat", "--check"]),
                append_files=True,
                description="Check Markdown formatting without changes.",
            ),
        ),
        languages=("markdown",),
        file_extensions=(".md", ".markdown", ".mdx"),
        description="Markdown formatter.",
        runtime="python",
        package="mdformat",
        min_version="0.7.22",
        version_command=("mdformat", "--version"),
    )

    yield Tool(
        name="sqlfluff",
        actions=(
            ToolAction(
                name="lint",
                command=_SqlfluffCommand(base=("sqlfluff", "lint", "--format", "json")),
                append_files=True,
                description="Lint SQL files using sqlfluff.",
                parser=JsonParser(parse_sqlfluff),
            ),
            ToolAction(
                name="fix",
                command=_SqlfluffCommand(base=("sqlfluff", "fix", "--force"), is_fix=True),
                append_files=True,
                is_fix=True,
                description="Autofix SQL files via sqlfluff fix.",
            ),
        ),
        languages=("sql",),
        file_extensions=(".sql",),
        description="SQL linter and formatter using sqlfluff.",
        runtime="python",
        package="sqlfluff",
        min_version="3.1.0",
        version_command=("sqlfluff", "--version"),
    )

    yield Tool(
        name="actionlint",
        actions=(
            ToolAction(
                name="lint",
                command=_ActionlintCommand(version=ACTIONLINT_VERSION_DEFAULT),
                append_files=False,
                description="Lint GitHub Actions workflows with actionlint.",
                parser=JsonParser(parse_actionlint),
            ),
        ),
        languages=("github-actions",),
        file_extensions=(".yml", ".yaml"),
        description="GitHub Actions workflow linter.",
        runtime="binary",
    )

    yield Tool(
        name="kube-linter",
        actions=(
            ToolAction(
                name="lint",
                command=_KubeLinterCommand(base=("kube-linter", "lint", "--format", "json")),
                append_files=True,
                description="Analyze Kubernetes manifests with kube-linter.",
                parser=JsonParser(parse_kube_linter),
            ),
        ),
        languages=("kubernetes",),
        file_extensions=(".yml", ".yaml"),
        description="Kubernetes deployment misconfiguration detector.",
        runtime="go",
        package="golang.stackrox.io/kube-linter/cmd/kube-linter@v0.7.6",
        min_version="0.7.6",
        version_command=("kube-linter", "version"),
        default_enabled=False,
    )

    yield Tool(
        name="eslint",
        actions=(
            ToolAction(
                name="lint",
                command=_EslintCommand(base=("eslint", "--format", "json")),
                append_files=True,
                description="Lint JavaScript/TypeScript sources using ESLint.",
                parser=JsonParser(parse_eslint),
            ),
            ToolAction(
                name="fix",
                command=_EslintCommand(base=("eslint", "--fix"), is_fix=True),
                append_files=True,
                is_fix=True,
                description="Autofix issues reported by ESLint.",
            ),
        ),
        languages=("javascript", "typescript"),
        file_extensions=(".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"),
        description="JavaScript/TypeScript linting via ESLint.",
        runtime="npm",
        package="eslint@9.13.0",
        min_version="9.13.0",
        version_command=("eslint", "--version"),
    )

    yield Tool(
        name="gts",
        actions=(
            ToolAction(
                name="lint",
                command=_GtsCommand(base=("gts", "lint", "--", "--format", "json")),
                append_files=True,
                description="Run Google's TypeScript style checks via gts.",
                parser=JsonParser(parse_eslint),
            ),
            ToolAction(
                name="fix",
                command=_GtsCommand(base=("gts", "fix"), is_fix=True),
                append_files=True,
                is_fix=True,
                description="Apply gts formatting and fixes.",
            ),
        ),
        languages=("javascript",),
        file_extensions=(".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"),
        description="Google TypeScript style checker.",
        runtime="npm",
        package="gts@5.3.1",
        min_version="5.3.1",
        version_command=("gts", "--version"),
    )

    yield Tool(
        name="stylelint",
        actions=(
            ToolAction(
                name="lint",
                command=_StylelintCommand(base=("stylelint",)),
                append_files=True,
                description="Lint stylesheets using stylelint.",
                parser=JsonParser(parse_stylelint),
            ),
            ToolAction(
                name="fix",
                command=_StylelintCommand(base=("stylelint", "--fix"), is_fix=True),
                append_files=True,
                is_fix=True,
                description="Apply stylelint autofixes.",
            ),
        ),
        languages=("css",),
        file_extensions=(".css", ".scss", ".sass", ".less"),
        description="CSS and preprocessor linting via stylelint.",
        runtime="npm",
        package="stylelint@16.11.0",
        min_version="16.11.0",
        version_command=("stylelint", "--version"),
    )

    yield Tool(
        name="prettier",
        actions=(
            ToolAction(
                name="format",
                command=_PrettierCommand(base=("prettier", "--write")),
                append_files=True,
                is_fix=True,
                description="Format files with Prettier.",
            ),
            ToolAction(
                name="check",
                command=_PrettierCommand(base=("prettier", "--check")),
                append_files=True,
                description="Verify Prettier formatting without modifying files.",
            ),
        ),
        languages=("javascript",),
        file_extensions=(
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".mjs",
            ".cjs",
            ".json",
            ".md",
            ".yaml",
            ".yml",
        ),
        description="Code formatter for JavaScript and related assets.",
        runtime="npm",
        package="prettier@3.3.3",
        min_version="3.3.0",
        version_command=("prettier", "--version"),
    )

    yield Tool(
        name="tsc",
        actions=(
            ToolAction(
                name="type-check",
                command=_TscCommand(base=("tsc", "--noEmit", "--pretty", "false")),
                append_files=False,
                description="Type-check TypeScript projects via tsc.",
                parser=TextParser(parse_tsc),
            ),
        ),
        languages=("javascript",),
        file_extensions=(".ts", ".tsx"),
        description="TypeScript compiler in check-only mode.",
        runtime="npm",
        package="typescript@5.6.3",
        min_version="5.6.3",
        version_command=("tsc", "--version"),
    )

    yield Tool(
        name="golangci-lint",
        actions=(
            ToolAction(
                name="lint",
                command=_GolangciLintCommand(base=("golangci-lint", "run", "--out-format", "json")),
                append_files=False,
                description="Run golangci-lint across Go packages.",
                parser=JsonParser(parse_golangci_lint),
            ),
        ),
        languages=("go",),
        file_extensions=(".go",),
        description="Aggregated Go lint tool using golangci-lint.",
        runtime="go",
        package="github.com/golangci/golangci-lint/cmd/golangci-lint@v1.60.3",
        min_version="1.60.3",
        version_command=("golangci-lint", "--version"),
    )

    yield Tool(
        name="gofmt",
        actions=(
            ToolAction(
                name="format",
                command=DeferredCommand(["gofmt", "-w"]),
                append_files=True,
                is_fix=True,
                description="Format Go source files with gofmt.",
            ),
            ToolAction(
                name="check",
                command=DeferredCommand(["gofmt", "-l"]),
                append_files=True,
                description="List Go files requiring gofmt.",
                parser=TextParser(_parse_gofmt_check),
            ),
        ),
        languages=("go",),
        file_extensions=(".go",),
        description="Go formatter.",
        runtime="binary",
        version_command=("go", "version"),
    )

    yield Tool(
        name="cargo-clippy",
        actions=(
            ToolAction(
                name="lint",
                command=DeferredCommand(["cargo", "clippy", "--message-format=json"]),
                append_files=False,
                description="Run Rust Clippy lints.",
                parser=JsonParser(parse_cargo_clippy),
            ),
        ),
        languages=("rust",),
        file_extensions=(".rs",),
        description="Rust linting via cargo clippy.",
        runtime="binary",
        min_version="1.81.0",
        version_command=("cargo", "--version"),
    )

    yield Tool(
        name="cargo-fmt",
        actions=(
            ToolAction(
                name="format",
                command=DeferredCommand(["cargo", "fmt"]),
                append_files=False,
                is_fix=True,
                description="Format Rust code using rustfmt.",
            ),
            ToolAction(
                name="check",
                command=DeferredCommand(["cargo", "fmt", "--check"]),
                append_files=False,
                description="Verify Rust formatting without changes.",
            ),
        ),
        languages=("rust",),
        file_extensions=(".rs",),
        description="Rust formatter via cargo fmt.",
        runtime="binary",
        version_command=("rustfmt", "--version"),
    )


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
