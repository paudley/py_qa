# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests covering propagation of tool-specific configuration settings."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from pyqa.config import Config
from pyqa.tools.base import Tool, ToolContext
from pyqa.tools.builtin_registry import initialize_registry
from pyqa.tools.registry import ToolRegistry


def _tool(name: str) -> Tool:
    registry = _catalog_registry()
    result = registry.try_get(name)
    if result is None:
        raise AssertionError(f"Tool {name} missing")
    return result


@lru_cache(maxsize=1)
def _catalog_registry() -> ToolRegistry:
    registry = ToolRegistry()
    initialize_registry(registry=registry)
    return registry


def test_ruff_settings_inject_flags(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["ruff"] = {
        "select": ["E", "F"],
        "target-version": "py311",
        "config": "config/ruff.toml",
        "args": ["--show-source"],
    }
    root = tmp_path
    (root / "config").mkdir()
    (root / "config" / "ruff.toml").write_text("", encoding="utf-8")

    tool = _tool("ruff")
    action = next(act for act in tool.actions if act.name == "lint")
    ctx = ToolContext(
        cfg=cfg,
        root=root,
        files=[root / "foo.py"],
        settings=cfg.tool_settings["ruff"],
    )

    cmd = action.build_command(ctx)
    assert "--select" in cmd and "E,F" in cmd
    assert "--target-version" in cmd and "py311" in cmd
    assert "--config" in cmd
    assert any("ruff.toml" in part for part in cmd)
    assert "--show-source" in cmd
    assert str(root / "foo.py") in cmd


def test_ruff_defaults_target_version(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.python_version = "3.12"
    tool = _tool("ruff")
    action = next(act for act in tool.actions if act.name == "lint")
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "foo.py"],
        settings=cfg.tool_settings.setdefault("ruff", {}),
    )

    cmd = action.build_command(ctx)
    assert "--target-version" in cmd
    assert cmd[cmd.index("--target-version") + 1] == "py312"


def test_black_settings_inject_flags(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["black"] = {
        "line-length": 100,
        "target-version": ["py311"],
        "preview": True,
        "args": ["--diff"],
    }

    tool = _tool("black")
    action = next(act for act in tool.actions if act.name == "check")
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "foo.py"],
        settings=cfg.tool_settings["black"],
    )

    cmd = action.build_command(ctx)
    assert "--line-length" in cmd and "100" in cmd
    assert "--target-version" in cmd and "py311" in cmd
    assert "--preview" in cmd
    assert "--diff" in cmd


def test_black_defaults_target_version(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.python_version = "3.10"
    tool = _tool("black")
    action = next(act for act in tool.actions if act.name == "check")
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "foo.py"],
        settings=cfg.tool_settings.setdefault("black", {}),
    )

    cmd = action.build_command(ctx)
    assert "--target-version" in cmd
    assert cmd[cmd.index("--target-version") + 1] == "py310"


def test_bandit_settings_extend_command(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["bandit"] = {
        "severity": "medium",
        "confidence": "high",
        "format": "txt",
        "baseline": "baseline.json",
        "exclude": ["third_party"],
        "targets": ["custom"],
        "args": ["--quiet"],
    }

    (tmp_path / "baseline.json").write_text("{}", encoding="utf-8")
    (tmp_path / "custom").mkdir()

    tool = _tool("bandit")
    action = tool.actions[0]
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[],
        settings=cfg.tool_settings["bandit"],
    )

    cmd = action.build_command(ctx)
    assert "--severity-level" in cmd and "medium" in cmd
    assert "--confidence-level" in cmd and "high" in cmd
    assert "--format" in cmd and "txt" in cmd
    assert "--baseline" in cmd
    assert "--skip" not in cmd
    assert "--quiet" in cmd
    assert any(str((tmp_path / "custom").resolve()) in part for part in cmd)


def test_isort_settings(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["isort"] = {
        "line-length": 120,
        "profile": "black",
        "skip": ["__init__.py"],
        "src": ["src"],
        "args": ["--color"],
    }

    (tmp_path / "src").mkdir()

    tool = _tool("isort")
    action = next(act for act in tool.actions if act.name == "sort")
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "mod.py"],
        settings=cfg.tool_settings["isort"],
    )

    cmd = action.build_command(ctx)
    assert "--line-length" in cmd and "120" in cmd
    assert "--profile" in cmd and "black" in cmd
    assert "--skip" in cmd and "__init__.py" in cmd
    assert "--src" in cmd and str((tmp_path / "src").resolve()) in cmd
    assert "--color" in cmd


def test_isort_defaults_python_version(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.python_version = "3.11"
    tool = _tool("isort")
    action = next(act for act in tool.actions if act.name == "sort")
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "mod.py"],
        settings=cfg.tool_settings.setdefault("isort", {}),
    )

    cmd = action.build_command(ctx)
    assert "--py" in cmd
    assert cmd[cmd.index("--py") + 1] == "311"


def test_isort_defaults_profile_black(tmp_path: Path) -> None:
    cfg = Config()
    tool = _tool("isort")
    action = next(act for act in tool.actions if act.name == "sort")
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "src" / "mod.py"],
        settings=cfg.tool_settings.setdefault("isort", {}),
    )

    cmd = action.build_command(ctx)
    assert "--profile" in cmd
    assert cmd[cmd.index("--profile") + 1] == "black"


def test_pylint_settings(tmp_path: Path) -> None:
    rc = tmp_path / "pylintrc"
    rc.write_text("", encoding="utf-8")

    cfg = Config()
    cfg.tool_settings["pylint"] = {
        "rcfile": "pylintrc",
        "disable": ["C0114"],
        "exit-zero": True,
    }

    tool = _tool("pylint")
    action = tool.actions[0]
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "module.py"],
        settings=cfg.tool_settings["pylint"],
    )

    cmd = action.build_command(ctx)
    assert "--rcfile" in cmd and str(rc) in cmd
    assert "--disable" in cmd and "C0114" in cmd
    assert "--exit-zero" in cmd
    expected_py = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert "--py-version" in cmd and expected_py in cmd
    assert "--max-complexity" in cmd and "10" in cmd
    assert "--max-args" in cmd and "5" in cmd


def test_pylint_init_import_flag(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["pylint"] = {"init-import": True}

    tool = _tool("pylint")
    action = tool.actions[0]
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "module.py"],
        settings=cfg.tool_settings["pylint"],
    )

    cmd = action.build_command(ctx)
    assert "--init-import=y" in cmd


def test_pylint_init_import_false(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["pylint"] = {"init-import": False}

    tool = _tool("pylint")
    action = tool.actions[0]
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "module.py"],
        settings=cfg.tool_settings["pylint"],
    )

    cmd = action.build_command(ctx)
    assert "--init-import=n" in cmd


def test_mypy_defaults_include_strict_flags(tmp_path: Path) -> None:
    cfg = Config()
    tool = _tool("mypy")
    action = tool.actions[0]

    module = tmp_path / "module.py"
    module.write_text("from typing import Any\n", encoding="utf-8")

    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[module],
        settings=cfg.tool_settings["mypy"],
    )

    cmd = action.build_command(ctx)
    expected_flags = {
        "--strict",
        "--warn-unused-ignores",
        "--warn-redundant-casts",
        "--warn-unreachable",
        "--disallow-untyped-decorators",
        "--disallow-any-generics",
        "--check-untyped-defs",
        "--no-implicit-reexport",
        "--show-error-codes",
        "--show-column-numbers",
        "--exclude-gitignore",
        "--sqlite-cache",
    }
    for flag in expected_flags:
        assert flag in cmd


def test_mypy_defaults_python_version(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.python_version = "3.9"
    tool = _tool("mypy")
    action = tool.actions[0]
    module = tmp_path / "module.py"
    module.write_text("print('hi')\n", encoding="utf-8")
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[module],
        settings=cfg.tool_settings.setdefault("mypy", {}),
    )

    cmd = action.build_command(ctx)
    assert "--python-version" in cmd
    assert cmd[cmd.index("--python-version") + 1] == "3.9"


def test_pylint_defaults_include_plugins(tmp_path: Path) -> None:
    cfg = Config()
    tool = _tool("pylint")
    action = tool.actions[0]

    module = tmp_path / "module.py"
    module.write_text("print('hello')\n", encoding="utf-8")

    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[module],
        settings=cfg.tool_settings.get("pylint", {}),
    )

    cmd = action.build_command(ctx)
    assert "--load-plugins" in cmd
    load_index = cmd.index("--load-plugins")
    plugins_arg = cmd[load_index + 1]
    assert "pylint.extensions.docparams" in plugins_arg


def test_pyright_settings(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["pyright"] = {
        "project": "pyprojectconfig.json",
        "python-version": "3.11",
        "args": ["--warnings"],
    }

    (tmp_path / "pyprojectconfig.json").write_text("{}", encoding="utf-8")

    tool = _tool("pyright")
    action = tool.actions[0]
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[],
        settings=cfg.tool_settings["pyright"],
    )

    cmd = action.build_command(ctx)
    assert "--project" in cmd and str((tmp_path / "pyprojectconfig.json").resolve()) in cmd
    assert "--pythonversion" in cmd and "3.11" in cmd
    assert "--warnings" in cmd


def test_pyright_defaults_python_version(tmp_path: Path) -> None:
    cfg = Config()
    cfg.execution.python_version = "3.8"
    tool = _tool("pyright")
    action = tool.actions[0]
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[],
        settings=cfg.tool_settings.setdefault("pyright", {}),
    )

    cmd = action.build_command(ctx)
    assert "--pythonversion" in cmd
    assert cmd[cmd.index("--pythonversion") + 1] == "3.8"


def test_pyupgrade_defaults(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["pyupgrade"] = {}
    tool = _tool("pyupgrade")
    action = tool.actions[0]
    source = tmp_path / "module.py"
    source.write_text("print('hi')\n", encoding="utf-8")
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[source],
        settings=cfg.tool_settings["pyupgrade"],
    )

    cmd = action.build_command(ctx)
    expected_flag = f"--py{sys.version_info.major}{sys.version_info.minor}-plus"
    assert expected_flag in cmd
    assert str(source) in cmd


def test_pyupgrade_settings(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["pyupgrade"] = {
        "pyplus": "py38",
        "keep-mock": True,
        "args": ["--exit-zero-even-if-changed"],
    }
    source = tmp_path / "util.py"
    source.write_text("print('bye')\n", encoding="utf-8")

    tool = _tool("pyupgrade")
    action = tool.actions[0]
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[source],
        settings=cfg.tool_settings["pyupgrade"],
    )

    cmd = action.build_command(ctx)
    assert "--py38-plus" in cmd
    assert "--keep-mock" in cmd
    assert "--exit-zero-even-if-changed" in cmd


def test_eslint_settings(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["eslint"] = {
        "config": "eslint.config.js",
        "ext": [".ts"],
        "max-warnings": 0,
        "cache": True,
        "args": ["--no-inline-config"],
    }

    (tmp_path / "eslint.config.js").write_text("", encoding="utf-8")

    tool = _tool("eslint")
    action = next(act for act in tool.actions if act.name == "lint")
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "app.ts"],
        settings=cfg.tool_settings["eslint"],
    )

    cmd = action.build_command(ctx)
    assert "--config" in cmd and str((tmp_path / "eslint.config.js").resolve()) in cmd
    assert "--ext" in cmd and ".ts" in cmd
    assert "--max-warnings" in cmd and "0" in cmd
    assert "--cache" in cmd
    assert "--no-inline-config" in cmd


def test_prettier_settings(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["prettier"] = {
        "config": "prettier.config.cjs",
        "single-quote": True,
        "tab-width": 2,
        "parser": "typescript",
        "args": ["--no-error-on-unmatched-pattern"],
    }

    (tmp_path / "prettier.config.cjs").write_text("", encoding="utf-8")

    tool = _tool("prettier")
    action = next(act for act in tool.actions if act.name == "format")
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[tmp_path / "main.ts"],
        settings=cfg.tool_settings["prettier"],
    )

    cmd = action.build_command(ctx)
    assert "--config" in cmd and str((tmp_path / "prettier.config.cjs").resolve()) in cmd
    assert "--single-quote" in cmd
    assert "--tab-width" in cmd and "2" in cmd
    assert "--parser" in cmd and "typescript" in cmd
    assert "--no-error-on-unmatched-pattern" in cmd


def test_tsc_settings(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["tsc"] = {
        "project": "tsconfig.json",
        "watch": True,
    }

    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")

    tool = _tool("tsc")
    action = tool.actions[0]
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[],
        settings=cfg.tool_settings["tsc"],
    )

    cmd = action.build_command(ctx)
    assert "--project" in cmd and str((tmp_path / "tsconfig.json").resolve()) in cmd
    assert "--watch" in cmd


def test_golangci_settings(tmp_path: Path) -> None:
    cfg = Config()
    cfg.tool_settings["golangci-lint"] = {
        "config": "golangci.yml",
        "enable": ["gofmt"],
        "disable": ["lll"],
        "deadline": "2m",
    }

    (tmp_path / "golangci.yml").write_text("", encoding="utf-8")

    tool = _tool("golangci-lint")
    action = tool.actions[0]
    ctx = ToolContext(
        cfg=cfg,
        root=tmp_path,
        files=[],
        settings=cfg.tool_settings["golangci-lint"],
    )

    cmd = action.build_command(ctx)
    assert "--config" in cmd and str((tmp_path / "golangci.yml").resolve()) in cmd
    assert "--enable" in cmd and "gofmt" in cmd
    assert "--disable" in cmd and "lll" in cmd
    assert "--deadline" in cmd and "2m" in cmd
