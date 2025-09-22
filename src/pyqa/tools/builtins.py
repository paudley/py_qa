"""Registration helpers for the built-in tool suite."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from ..models import RawDiagnostic
from ..parsers import (
    JsonParser,
    TextParser,
    parse_bandit,
    parse_cargo_clippy,
    parse_eslint,
    parse_golangci_lint,
    parse_mypy,
    parse_pylint,
    parse_pyright,
    parse_ruff,
    parse_tsc,
)
from ..severity import Severity
from .base import CommandBuilder, DeferredCommand, Tool, ToolAction, ToolContext
from .registry import DEFAULT_REGISTRY, ToolRegistry


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
        cmd = list(self.base_args)
        root = ctx.root

        exclude_paths: set[Path] = set()
        exclude_args: set[str] = set()
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
                command=DeferredCommand(
                    ["ruff", "check", "--force-exclude", "--output-format", "json"]
                ),
                append_files=True,
                description="Run ruff against the discovered Python files.",
                parser=JsonParser(parse_ruff),
            ),
            ToolAction(
                name="fix",
                command=DeferredCommand(["ruff", "check", "--fix", "--force-exclude"]),
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
                command=DeferredCommand(["black"]),
                append_files=True,
                is_fix=True,
                description="Format Python sources using Black.",
            ),
            ToolAction(
                name="check",
                command=DeferredCommand(["black", "--check"]),
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
                command=DeferredCommand(["mypy", "--output", "json"]),
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
                command=DeferredCommand(["ruff", "format", "--force-exclude"]),
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
                command=DeferredCommand(["isort"]),
                append_files=True,
                is_fix=True,
                description="Apply import sorting with isort.",
            ),
            ToolAction(
                name="check",
                command=DeferredCommand(["isort", "--check-only"]),
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
                command=DeferredCommand(["pylint", "--output-format=json"]),
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
                command=DeferredCommand(["pyright", "--outputjson"]),
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
        name="eslint",
        actions=(
            ToolAction(
                name="lint",
                command=DeferredCommand(["eslint", "--format", "json"]),
                append_files=True,
                description="Lint JavaScript/TypeScript sources using ESLint.",
                parser=JsonParser(parse_eslint),
            ),
            ToolAction(
                name="fix",
                command=DeferredCommand(["eslint", "--fix"]),
                append_files=True,
                is_fix=True,
                description="Autofix issues reported by ESLint.",
            ),
        ),
        languages=("javascript",),
        file_extensions=(".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"),
        description="JavaScript/TypeScript linting via ESLint.",
        runtime="npm",
        package="eslint@9.13.0",
        min_version="9.13.0",
        version_command=("eslint", "--version"),
    )

    yield Tool(
        name="prettier",
        actions=(
            ToolAction(
                name="format",
                command=DeferredCommand(["prettier", "--write"]),
                append_files=True,
                is_fix=True,
                description="Format files with Prettier.",
            ),
            ToolAction(
                name="check",
                command=DeferredCommand(["prettier", "--check"]),
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
                command=DeferredCommand(["tsc", "--noEmit", "--pretty", "false"]),
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
                command=DeferredCommand(
                    ["golangci-lint", "run", "--out-format", "json"]
                ),
                append_files=False,
                description="Run golangci-lint across Go packages.",
                parser=JsonParser(parse_golangci_lint),
            ),
        ),
        languages=("go",),
        file_extensions=(".go",),
        description="Aggregated Go lint tool using golangci-lint.",
        runtime="binary",
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
