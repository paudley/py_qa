# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Python-centric built-in tool definitions."""

from __future__ import annotations

from collections.abc import Iterable

from ..parsers import (
    JsonParser,
    TextParser,
    parse_bandit,
    parse_cpplint,
    parse_mypy,
    parse_pylint,
    parse_pyright,
    parse_ruff,
    parse_sqlfluff,
    parse_tombi,
)
from .base import DeferredCommand, Tool, ToolAction
from .builtin_commands import (
    _BanditCommand,
    _BlackCommand,
    _CpplintCommand,
    _IsortCommand,
    _MypyCommand,
    _PylintCommand,
    _PyrightCommand,
    _PyupgradeCommand,
    _RuffCommand,
    _RuffFormatCommand,
    _SqlfluffCommand,
    _TombiCommand,
)


def python_tools() -> Iterable[Tool]:
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
                ignore_exit=True,
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
                ignore_exit=True,
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
                ignore_exit=True,
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
                ignore_exit=True,
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
        name="pyupgrade",
        actions=(
            ToolAction(
                name="fix",
                command=_PyupgradeCommand(base=("pyupgrade",)),
                append_files=True,
                description="Modernize Python syntax using pyupgrade.",
                is_fix=True,
            ),
        ),
        languages=("python",),
        file_extensions=(".py", ".pyi"),
        description="Automated Python syntax upgrades via pyupgrade.",
        runtime="python",
        package="pyupgrade",
        min_version="3.19.1",
        version_command=("pyupgrade", "--version"),
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
        name="tombi",
        actions=(
            ToolAction(
                name="lint",
                command=_TombiCommand(base=("tombi", "lint")),
                append_files=True,
                description="Lint TOML files using Tombi.",
                parser=TextParser(parse_tombi),
            ),
        ),
        languages=("toml",),
        file_extensions=(".toml",),
        config_files=("tombi.toml",),
        description="TOML toolkit providing linting via tombi.",
        runtime="python",
        package="tombi",
        min_version="0.6.12",
        version_command=("tombi", "--version"),
    )
    yield Tool(
        name="cpplint",
        actions=(
            ToolAction(
                name="lint",
                command=_CpplintCommand(base=("cpplint", "--output=emacs")),
                append_files=True,
                description="Lint C and C++ sources with cpplint.",
                parser=TextParser(parse_cpplint),
            ),
        ),
        languages=("cpp",),
        file_extensions=(
            ".c",
            ".cc",
            ".cpp",
            ".cxx",
            ".c++",
            ".cu",
            ".cuh",
            ".h",
            ".hh",
            ".hpp",
            ".h++",
            ".hxx",
        ),
        config_files=("CPPLINT.cfg",),
        description="Google style C/C++ linter.",
        runtime="python",
        package="cpplint",
        min_version="2.0.2",
        version_command=("cpplint", "--version"),
    )


__all__ = [
    "python_tools",
]
