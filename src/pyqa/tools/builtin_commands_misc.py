# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
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
)


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


__all__ = [
    "_GolangciLintCommand",
    "_StylelintCommand",
    "_TscCommand",
]
