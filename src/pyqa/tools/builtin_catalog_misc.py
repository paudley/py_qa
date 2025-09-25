# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Miscellaneous built-in tool definitions."""

from __future__ import annotations

from collections.abc import Iterable

from ..parsers import (
    JsonParser,
    TextParser,
    parse_actionlint,
    parse_cargo_clippy,
    parse_checkmake,
    parse_dockerfilelint,
    parse_dotenv_linter,
    parse_eslint,
    parse_golangci_lint,
    parse_hadolint,
    parse_kube_linter,
    parse_luacheck,
    parse_lualint,
    parse_perlcritic,
    parse_phplint,
    parse_remark,
    parse_selene,
    parse_shfmt,
    parse_speccy,
    parse_stylelint,
    parse_tsc,
    parse_yamllint,
)
from .base import DeferredCommand, Tool, ToolAction
from .builtin_commands import (
    _ActionlintCommand,
    _CheckmakeCommand,
    _DockerfilelintCommand,
    _DotenvLinterCommand,
    _EslintCommand,
    _GolangciLintCommand,
    _GtsCommand,
    _HadolintCommand,
    _KubeLinterCommand,
    _LuacheckCommand,
    _LualintCommand,
    _PerlCriticCommand,
    _PerltidyCommand,
    _PhplintCommand,
    _PrettierCommand,
    _RemarkCommand,
    _SeleneCommand,
    _ShfmtCommand,
    _SpeccyCommand,
    _StylelintCommand,
    _TscCommand,
    _YamllintCommand,
)
from .builtin_helpers import (
    _CARGO_AVAILABLE,
    _CPANM_AVAILABLE,
    _LUA_AVAILABLE,
    _LUAROCKS_AVAILABLE,
    ACTIONLINT_VERSION_DEFAULT,
    HADOLINT_VERSION_DEFAULT,
    _parse_gofmt_check,
)


def misc_tools() -> Iterable[Tool]:
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
        name="remark-lint",
        actions=(
            ToolAction(
                name="lint",
                command=_RemarkCommand(base=("remark", "--use", "remark-preset-lint-recommended")),
                append_files=True,
                description="Lint Markdown files using remark-lint recommended rules.",
                parser=JsonParser(parse_remark),
                ignore_exit=True,
            ),
            ToolAction(
                name="fix",
                command=_RemarkCommand(
                    base=("remark", "--use", "remark-preset-lint-recommended"),
                    is_fix=True,
                ),
                append_files=False,
                is_fix=True,
                description="Apply remark formatting fixes.",
            ),
        ),
        languages=("markdown",),
        file_extensions=(".md", ".mdx", ".markdown"),
        description="Markdown linting via remark-lint preset.",
        runtime="npm",
        package="remark-cli@12.0.1 remark-lint@9.1.2 remark-preset-lint-recommended@6.1.3 vfile-reporter-json@4.0.0",
        min_version="12.0.1",
        version_command=("remark", "--version"),
    )
    yield Tool(
        name="speccy",
        actions=(
            ToolAction(
                name="lint",
                command=_SpeccyCommand(base=("speccy", "lint")),
                append_files=True,
                description="Lint OpenAPI specs using Speccy.",
                parser=JsonParser(parse_speccy),
            ),
        ),
        languages=("openapi",),
        file_extensions=(
            "openapi.yaml",
            "openapi.yml",
            "swagger.yaml",
            "swagger.yml",
            "speccy.yaml",
            "speccy.yml",
        ),
        description="OpenAPI linter powered by Speccy.",
        runtime="npm",
        package="speccy@0.11.0",
        min_version="0.11.0",
        version_command=("speccy", "--version"),
    )
    yield Tool(
        name="perltidy",
        actions=(
            ToolAction(
                name="format",
                command=_PerltidyCommand(base=("perltidy",), is_fix=True),
                append_files=True,
                is_fix=True,
                description="Format Perl code using perltidy.",
            ),
            ToolAction(
                name="check",
                command=_PerltidyCommand(base=("perltidy",), is_fix=False),
                append_files=True,
                description="Verify Perl formatting without modifying files.",
            ),
        ),
        languages=("perl",),
        file_extensions=(".pl", ".pm", ".t", ".phtml"),
        description="Perl formatter using perltidy.",
        runtime="perl",
        package="Perl::Tidy",
        min_version="20240112",
        version_command=("perltidy", "--version"),
        default_enabled=_CPANM_AVAILABLE,
    )
    yield Tool(
        name="perlcritic",
        actions=(
            ToolAction(
                name="lint",
                command=_PerlCriticCommand(base=("perlcritic",)),
                append_files=True,
                description="Run Perl::Critic static analysis.",
                parser=TextParser(parse_perlcritic),
            ),
        ),
        languages=("perl",),
        file_extensions=(".pl", ".pm", ".t", ".phtml"),
        description="Perl static analysis via Perl::Critic.",
        runtime="perl",
        package="Perl::Critic",
        min_version="1.151",
        version_command=("perlcritic", "--version"),
        default_enabled=_CPANM_AVAILABLE,
    )
    yield Tool(
        name="shfmt",
        actions=(
            ToolAction(
                name="format",
                command=_ShfmtCommand(base=("shfmt",), is_fix=True),
                append_files=True,
                is_fix=True,
                description="Format shell scripts using shfmt.",
            ),
            ToolAction(
                name="check",
                command=_ShfmtCommand(base=("shfmt",), is_fix=False),
                append_files=True,
                description="Verify shell script formatting without modifying files.",
                parser=TextParser(parse_shfmt),
            ),
        ),
        languages=("shell",),
        file_extensions=(".sh", ".bash", ".zsh"),
        description="Shell script formatter.",
        runtime="go",
        package="mvdan.cc/sh/v3/cmd/shfmt@v3.9.0",
        min_version="3.9.0",
        version_command=("shfmt", "--version"),
    )
    yield Tool(
        name="phplint",
        actions=(
            ToolAction(
                name="lint",
                command=_PhplintCommand(base=("phplint",)),
                append_files=True,
                description="Lint PHP files using phplint.",
                parser=TextParser(parse_phplint),
            ),
        ),
        languages=("php",),
        file_extensions=(".php", ".phtml"),
        description="PHP syntax linter via phplint.",
        runtime="npm",
        package="phplint@2.0.5",
        min_version="2.0.5",
        version_command=("phplint", "--version"),
    )
    yield Tool(
        name="checkmake",
        actions=(
            ToolAction(
                name="lint",
                command=_CheckmakeCommand(base=("checkmake", "lint")),
                append_files=True,
                description="Lint Makefiles using checkmake.",
                parser=JsonParser(parse_checkmake),
            ),
        ),
        languages=("make",),
        file_extensions=("Makefile", "makefile", ".mk"),
        description="Makefile linter powered by checkmake.",
        runtime="go",
        package="github.com/checkmake/checkmake/cmd/checkmake",
        min_version=None,
        version_command=("checkmake", "--version"),
    )
    yield Tool(
        name="yamllint",
        actions=(
            ToolAction(
                name="lint",
                command=_YamllintCommand(base=("yamllint",)),
                append_files=True,
                description="Lint YAML files using yamllint.",
                parser=TextParser(parse_yamllint),
            ),
        ),
        languages=("yaml",),
        file_extensions=(".yml", ".yaml"),
        description="YAML linter enforcing style and correctness rules.",
        runtime="python",
        package="yamllint",
        min_version="1.35.1",
        version_command=("yamllint", "--version"),
    )
    yield Tool(
        name="dockerfilelint",
        actions=(
            ToolAction(
                name="lint",
                command=_DockerfilelintCommand(base=("dockerfilelint", "--output", "json")),
                append_files=True,
                description="Analyze Dockerfiles with dockerfilelint.",
                parser=JsonParser(parse_dockerfilelint),
            ),
        ),
        languages=("docker",),
        file_extensions=("Dockerfile", "dockerfile", "Containerfile"),
        description="Dockerfile linter enforcing best practices.",
        runtime="npm",
        package="dockerfilelint@1.8.0",
        min_version="1.8.0",
        version_command=("dockerfilelint", "--version"),
    )
    yield Tool(
        name="hadolint",
        actions=(
            ToolAction(
                name="lint",
                command=_HadolintCommand(version=HADOLINT_VERSION_DEFAULT),
                append_files=True,
                description="Dockerfile analysis via hadolint.",
                parser=JsonParser(parse_hadolint),
            ),
        ),
        languages=("docker",),
        file_extensions=("Dockerfile", "dockerfile", "Containerfile"),
        description="Dockerfile linter based on ShellCheck and best practices.",
        runtime="binary",
    )
    yield Tool(
        name="dotenv-linter",
        actions=(
            ToolAction(
                name="lint",
                command=_DotenvLinterCommand(base=("dotenv-linter",)),
                append_files=True,
                description="Lint .env files using dotenv-linter.",
                parser=TextParser(parse_dotenv_linter),
            ),
        ),
        languages=("dotenv",),
        file_extensions=(".env", ".env.example", ".env.template", "env"),
        description="Rust-based linter for dotenv files.",
        runtime="rust",
        package="dotenv-linter",
        min_version="3.3.0",
        version_command=("dotenv-linter", "--version"),
        default_enabled=_CARGO_AVAILABLE,
    )
    yield Tool(
        name="lualint",
        actions=(
            ToolAction(
                name="lint",
                command=_LualintCommand(base=("lua",)),
                append_files=True,
                description="Static analysis for Lua globals via lualint.",
                parser=TextParser(parse_lualint),
            ),
        ),
        languages=("lua",),
        file_extensions=(".lua",),
        description="Lua bytecode-based global usage linter.",
        runtime="binary",
        default_enabled=_LUA_AVAILABLE,
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
        name="luacheck",
        actions=(
            ToolAction(
                name="lint",
                command=_LuacheckCommand(base=("luacheck",)),
                append_files=True,
                description="Lint Lua sources using luacheck.",
                parser=TextParser(parse_luacheck),
            ),
        ),
        languages=("lua",),
        file_extensions=(".lua",),
        description="Lua static analyzer supporting custom standards.",
        runtime="lua",
        package="luacheck",
        min_version="1.2.0",
        version_command=("luacheck", "--version"),
        default_enabled=_LUAROCKS_AVAILABLE,
    )
    yield Tool(
        name="selene",
        actions=(
            ToolAction(
                name="lint",
                command=_SeleneCommand(base=("selene",)),
                append_files=True,
                description="Lint Lua sources with Selene.",
                parser=JsonParser(parse_selene),
            ),
        ),
        languages=("lua",),
        file_extensions=(".lua",),
        config_files=("selene.toml",),
        description="Modern Lua linter powered by selene.",
        runtime="rust",
        package="selene",
        min_version="0.29.0",
        version_command=("selene", "--version"),
        default_enabled=_CARGO_AVAILABLE,
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
        runtime="rust",
        package="rustup:clippy",
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


__all__ = [
    "misc_tools",
]
