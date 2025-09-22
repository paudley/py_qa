# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests covering propagation of tool-specific configuration settings."""

from __future__ import annotations

from pathlib import Path

from pyqa.config import Config
from pyqa.tools import builtins as builtins_module
from pyqa.tools.base import ToolContext
from pyqa.tools.registry import ToolRegistry


def _tool(name: str):
    registry = ToolRegistry()
    for tool in builtins_module._builtin_tools():
        registry.register(tool)
    tool = registry.try_get(name)
    assert tool is not None, f"Tool {name} missing"
    return tool


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
