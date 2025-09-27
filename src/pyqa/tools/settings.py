# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Schema metadata describing supported tool-specific configuration keys."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class SettingField:
    """Structured representation of a tool configuration option."""

    type: str
    description: str
    enum: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum is not None:
            payload["enum"] = list(self.enum)
        return payload


ToolSettingField = Mapping[str, str | list[str]]
RawToolSettingSchema = dict[str, dict[str, ToolSettingField]]
ToolSettingSchema = dict[str, dict[str, SettingField]]


RAW_TOOL_SETTING_SCHEMA: RawToolSettingSchema = {
    "ruff": {
        "config": {
            "type": "path",
            "description": "Specific ruff configuration file to use.",
        },
        "select": {
            "type": "list[str]",
            "description": "Restrict linting to the provided ruff rule codes.",
        },
        "ignore": {
            "type": "list[str]",
            "description": "Ignore the listed ruff rule codes.",
        },
        "extend-select": {
            "type": "list[str]",
            "description": "Extend the default selection with additional rule codes.",
        },
        "extend-ignore": {
            "type": "list[str]",
            "description": "Extend the default ignored codes for the project.",
        },
        "line-length": {
            "type": "int",
            "description": "Override the maximum line length.",
        },
        "target-version": {
            "type": "str",
            "description": "Python version passed to ruff (e.g. py311).",
            "enum": ["py37", "py38", "py39", "py310", "py311", "py312", "py313"],
        },
        "per-file-ignores": {
            "type": "list[str]",
            "description": "List of pattern:codes entries for per-file ignores.",
        },
        "exclude": {
            "type": "list[str]",
            "description": "Paths or globs that ruff should exclude.",
        },
        "extend-exclude": {
            "type": "list[str]",
            "description": "Additional exclusion patterns applied after defaults.",
        },
        "respect-gitignore": {
            "type": "bool",
            "description": "Whether to honour .gitignore patterns during linting.",
        },
        "preview": {
            "type": "bool",
            "description": "Enable preview / unstable ruff rules.",
        },
        "unsafe-fixes": {
            "type": "bool",
            "description": "Allow fix actions that may alter runtime semantics.",
        },
        "fix": {
            "type": "bool",
            "description": "Enable --fix when running the lint action.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments appended to the ruff invocation.",
        },
    },
    "ruff-format": {
        "config": {
            "type": "path",
            "description": "Specific ruff formatter configuration file to use.",
        },
        "line-length": {
            "type": "int",
            "description": "Override formatter line length.",
        },
        "target-version": {
            "type": "str",
            "description": "Python version passed to the formatter.",
            "enum": ["py37", "py38", "py39", "py310", "py311", "py312", "py313"],
        },
        "exclude": {
            "type": "list[str]",
            "description": "Paths or globs to exclude from formatting.",
        },
        "extend-exclude": {
            "type": "list[str]",
            "description": "Additional exclusion patterns evaluated after defaults.",
        },
        "respect-gitignore": {
            "type": "bool",
            "description": "Whether to honour .gitignore during formatting.",
        },
        "preview": {
            "type": "bool",
            "description": "Enable preview / unstable formatting behaviour.",
        },
        "stdin-filename": {
            "type": "str",
            "description": "Filename to associate with STDIN content.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments for the formatter.",
        },
    },
    "black": {
        "config": {"type": "path", "description": "Black configuration file."},
        "line-length": {
            "type": "int",
            "description": "Maximum line length enforced by Black.",
        },
        "target-version": {
            "type": "list[str]",
            "description": "Allowed Python target versions (e.g. py311).",
            "enum": ["py37", "py38", "py39", "py310", "py311", "py312", "py313"],
        },
        "preview": {
            "type": "bool",
            "description": "Enable Black preview mode.",
        },
        "skip-string-normalization": {
            "type": "bool",
            "description": "Disable quote normalization transformations.",
        },
        "skip-magic-trailing-comma": {
            "type": "bool",
            "description": "Disable automatic trailing comma insertion.",
        },
        "workers": {
            "type": "int",
            "description": "Number of worker processes (-j).",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments appended to Black.",
        },
    },
    "isort": {
        "settings-path": {
            "type": "path",
            "description": "Explicit isort settings / config file path.",
        },
        "profile": {
            "type": "str",
            "description": "Profile to load (e.g. black).",
        },
        "line-length": {
            "type": "int",
            "description": "Override import wrap line length.",
        },
        "multi-line": {
            "type": "str",
            "description": "Multi-line output mode.",
            "enum": [
                "GRID",
                "VERTICAL",
                "VERTICAL_HANGING_INDENT",
                "VERTICAL_GRID",
                "VERTICAL_GRID_GROUPED",
                "VERTICAL_GRID_GROUPED_NO_COMMA",
                "VERTICAL_GRID_NO_COMMA",
                "HANGING_INDENT",
            ],
        },
        "src": {
            "type": "list[str]",
            "description": "Additional source roots for module resolution.",
        },
        "virtual-env": {
            "type": "path",
            "description": "Virtual environment directory passed to isort.",
        },
        "conda-env": {
            "type": "path",
            "description": "Conda environment directory passed to isort.",
        },
        "skip": {
            "type": "list[str]",
            "description": "Specific files or directories to skip.",
        },
        "extend-skip": {
            "type": "list[str]",
            "description": "Additional skip patterns appended to defaults.",
        },
        "skip-glob": {
            "type": "list[str]",
            "description": "File glob patterns excluded from processing.",
        },
        "extend-skip-glob": {
            "type": "list[str]",
            "description": "Extra glob patterns appended after defaults.",
        },
        "filter-files": {
            "type": "bool",
            "description": "Filter provided files to those supported by isort before execution.",
        },
        "float-to-top": {
            "type": "bool",
            "description": "Move from-style imports to the top of the file.",
        },
        "combine-as": {
            "type": "bool",
            "description": "Combine multiple as imports into a single import.",
        },
        "combine-star": {
            "type": "bool",
            "description": "Combine star imports from the same module.",
        },
        "color": {
            "type": "bool",
            "description": "Enable coloured output.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments appended to isort.",
        },
    },
    "eslint": {
        "config": {
            "type": "path",
            "description": "Custom eslint configuration file path.",
        },
        "ignore-path": {
            "type": "path",
            "description": "Path to eslint ignore file.",
        },
        "max-warnings": {
            "type": "int",
            "description": "Maximum warnings allowed before eslint exits non-zero.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments appended to the eslint invocation.",
        },
    },
    "stylelint": {
        "config": {
            "type": "path",
            "description": "Custom stylelint configuration file path.",
        },
        "ignore-path": {
            "type": "path",
            "description": "Path to stylelint ignore file.",
        },
        "max-warnings": {
            "type": "int",
            "description": "Maximum warnings allowed before stylelint exits non-zero.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments appended to the stylelint command.",
        },
    },
    "tsc": {
        "project": {
            "type": "path",
            "description": "Path passed to tsc via --project.",
        },
        "strict": {
            "type": "bool",
            "description": "Toggle TypeScript strict mode for linting runs.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional tsc arguments to append.",
        },
    },
    "mypy": {
        "exclude-gitignore": {
            "type": "bool",
            "description": "Respect .gitignore entries when discovering modules.",
        },
        "sqlite-cache": {
            "type": "bool",
            "description": "Enable SQLite cache backend for mypy.",
        },
        "config": {
            "type": "path",
            "description": "Custom mypy configuration file to load.",
        },
        "strict": {
            "type": "bool",
            "description": "Enable mypy strict mode.",
        },
        "ignore-missing-imports": {
            "type": "bool",
            "description": "Suppress errors about missing type information",
        },
        "namespace-packages": {
            "type": "bool",
            "description": "Treat packages without __init__.py as namespaces.",
        },
        "warn-unused-configs": {
            "type": "bool",
            "description": "Warn when config options are unused.",
        },
        "warn-return-any": {
            "type": "bool",
            "description": "Warn when returning Any typed values.",
        },
        "warn-redundant-casts": {
            "type": "bool",
            "description": "Warn when casting yields the same type.",
        },
        "warn-unused-ignores": {
            "type": "bool",
            "description": "Warn about unused # type: ignore directives.",
        },
        "warn-unreachable": {
            "type": "bool",
            "description": "Warn when statements are statically unreachable.",
        },
        "disallow-untyped-decorators": {
            "type": "bool",
            "description": "Error on decorators without type annotations.",
        },
        "disallow-any-generics": {
            "type": "bool",
            "description": "Error when using generic types with implicit Any.",
        },
        "check-untyped-defs": {
            "type": "bool",
            "description": "Type check function bodies with no type hints.",
        },
        "no-implicit-reexport": {
            "type": "bool",
            "description": "Disable implicit re-exporting of imported names.",
        },
        "show-error-codes": {
            "type": "bool",
            "description": "Display error codes alongside messages.",
        },
        "show-column-numbers": {
            "type": "bool",
            "description": "Include column numbers in diagnostic output.",
        },
        "python-version": {
            "type": "str",
            "description": "Python version string for type checking.",
        },
        "python-executable": {
            "type": "path",
            "description": "Interpreter executable used for type checking.",
        },
        "plugins": {
            "type": "list[str]",
            "description": "Mypy plugins to load via --plugin.",
        },
        "cache-dir": {
            "type": "path",
            "description": "Location for mypy cache data.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments passed to mypy.",
        },
    },
    "pylint": {
        "rcfile": {
            "type": "path",
            "description": "Path to pylintrc or equivalent configuration.",
        },
        "disable": {
            "type": "list[str]",
            "description": "Message symbols or groups to disable.",
        },
        "enable": {
            "type": "list[str]",
            "description": "Message symbols to enable in addition to defaults.",
        },
        "jobs": {
            "type": "int",
            "description": "Number of parallel workers.",
        },
        "fail-under": {
            "type": "float",
            "description": "Lower score boundary to fail the run.",
        },
        "exit-zero": {
            "type": "bool",
            "description": "Force exit code zero regardless of findings.",
        },
        "score": {
            "type": "bool",
            "description": "Enable/disable pylint score output.",
        },
        "reports": {
            "type": "bool",
            "description": "Enable/disable additional reports.",
        },
        "max-line-length": {
            "type": "int",
            "description": "Maximum allowed source line length.",
        },
        "max-complexity": {
            "type": "int",
            "description": "Upper bound for cyclomatic complexity.",
        },
        "max-args": {
            "type": "int",
            "description": "Maximum number of arguments permitted on functions/methods.",
        },
        "max-positional-arguments": {
            "type": "int",
            "description": "Maximum positional arguments allowed before flagging.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments appended to pylint.",
        },
    },
    "pyright": {
        "project": {
            "type": "path",
            "description": "Path to pyrightconfig/tsconfig project file.",
        },
        "venv-path": {
            "type": "path",
            "description": "Root directory containing virtual environments.",
        },
        "pythonpath": {
            "type": "path",
            "description": "Additional search path for module resolution.",
        },
        "typeshed-path": {
            "type": "path",
            "description": "Custom typeshed location.",
        },
        "python-platform": {
            "type": "str",
            "description": "Target execution platform (e.g. Linux, Darwin).",
            "enum": ["Linux", "Darwin", "Windows"],
        },
        "python-version": {
            "type": "str",
            "description": "Python version string to target.",
            "enum": ["3.7", "3.8", "3.9", "3.10", "3.11", "3.12", "3.13"],
        },
        "lib": {
            "type": "bool",
            "description": "Include library type information in the run.",
        },
        "verifytypes": {
            "type": "str",
            "description": "Module or pattern to verify using --verifytypes.",
        },
        "ignoreexternal": {
            "type": "bool",
            "description": "Ignore external type stubs.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments appended to pyright.",
        },
    },
    "bandit": {
        "exclude": {
            "type": "list[str]",
            "description": "Additional directories/files to exclude from scanning.",
        },
        "targets": {
            "type": "list[str]",
            "description": "Extra directories to include when scanning.",
        },
        "config": {
            "type": "path",
            "description": "Bandit configuration file path.",
        },
        "baseline": {
            "type": "path",
            "description": "Baseline results file path.",
        },
        "format": {
            "type": "str",
            "description": "Output format (json, txt, etc.).",
            "enum": ["json", "txt", "yaml", "xml"],
        },
        "severity": {
            "type": "str",
            "description": "Minimum severity level (low/medium/high).",
            "enum": ["low", "medium", "high"],
        },
        "confidence": {
            "type": "str",
            "description": "Minimum confidence level (low/medium/high).",
            "enum": ["low", "medium", "high"],
        },
        "skip": {
            "type": "list[str]",
            "description": "Tests to skip (e.g. S101).",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments appended to bandit.",
        },
    },
    "eslint": {
        "config": {
            "type": "path",
            "description": "ESLint configuration file or directory.",
        },
        "ext": {
            "type": "list[str]",
            "description": "Additional file extensions to lint.",
        },
        "ignore-path": {
            "type": "path",
            "description": "Custom .eslintignore file path.",
        },
        "resolve-plugins-relative-to": {
            "type": "path",
            "description": "Directory from which ESLint resolves plugins.",
        },
        "rulesdir": {
            "type": "list[str]",
            "description": "Directories containing custom ESLint rules.",
        },
        "max-warnings": {
            "type": "int",
            "description": "Exit with error if warnings exceed this count.",
        },
        "cache": {
            "type": "bool",
            "description": "Enable ESLint result caching.",
        },
        "cache-location": {
            "type": "path",
            "description": "Where ESLint stores cache data.",
        },
        "fix-type": {
            "type": "list[str]",
            "description": "Limit fixes to the given rule types.",
        },
        "quiet": {
            "type": "bool",
            "description": "Suppress reporting of warnings.",
        },
        "no-error-on-unmatched-pattern": {
            "type": "bool",
            "description": "Treat unmatched patterns as success instead of failure.",
        },
        "report-unused-disable-directives": {
            "type": "str",
            "description": "Control reporting for unused eslint-disable comments.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments appended to ESLint.",
        },
    },
    "luacheck": {
        "config": {
            "type": "path",
            "description": "luacheck configuration file.",
        },
        "std": {
            "type": "str",
            "description": "Standard globals set to load (e.g. luajit, love, ngx).",
        },
        "globals": {
            "type": "list[str]",
            "description": "Global identifiers treated as defined.",
        },
        "read-globals": {
            "type": "list[str]",
            "description": "Globals allowed for read-only access.",
        },
        "ignore": {
            "type": "list[str]",
            "description": "Diagnostic codes or patterns to ignore.",
        },
        "exclude-files": {
            "type": "list[str]",
            "description": "Paths or globs excluded from linting.",
        },
        "max-line-length": {
            "type": "int",
            "description": "Maximum permitted line length.",
        },
        "max-code-line-length": {
            "type": "int",
            "description": "Maximum length for code lines (excluding comments/strings).",
        },
        "max-string-line-length": {
            "type": "int",
            "description": "Maximum length for lines inside multi-line strings.",
        },
        "max-comment-line-length": {
            "type": "int",
            "description": "Maximum length for comment lines.",
        },
        "max-cyclomatic-complexity": {
            "type": "int",
            "description": "Upper limit for function cyclomatic complexity.",
        },
        "quiet": {
            "type": "bool",
            "description": "Suppress non-critical luacheck output.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments appended to luacheck.",
        },
    },
    "prettier": {
        "config": {
            "type": "path",
            "description": "Prettier configuration file to load.",
        },
        "parser": {
            "type": "str",
            "description": "Explicit parser (e.g. typescript, babel).",
        },
        "ignore-path": {
            "type": "path",
            "description": "Ignore file used during formatting.",
        },
        "plugin-search-dir": {
            "type": "list[str]",
            "description": "Directories used to resolve prettier plugins.",
        },
        "plugin": {
            "type": "list[str]",
            "description": "Additional prettier plugins to load.",
        },
        "loglevel": {
            "type": "str",
            "description": "Prettier log level (debug/info/warn/error).",
        },
        "config-precedence": {
            "type": "str",
            "description": "How multiple configs are merged (cli-override/file-override).",
        },
        "single-quote": {
            "type": "bool",
            "description": "Prefer single quotes when formatting.",
        },
        "tab-width": {
            "type": "int",
            "description": "Number of spaces per indentation level.",
        },
        "use-tabs": {
            "type": "bool",
            "description": "Indent with tabs instead of spaces.",
        },
        "trailing-comma": {
            "type": "str",
            "description": "Specify trailing comma behaviour (all, es5, none).",
            "enum": ["all", "es5", "none"],
        },
        "print-width": {
            "type": "int",
            "description": "Preferred line length before wrapping.",
        },
        "semi": {
            "type": "bool",
            "description": "Whether to add semicolons at statement ends.",
        },
        "end-of-line": {
            "type": "str",
            "description": "End-of-line style (lf, crlf, auto).",
            "enum": ["lf", "crlf", "cr", "auto"],
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments passed to prettier.",
        },
    },
    "tsc": {
        "project": {
            "type": "path",
            "description": "tsconfig project to use for the run.",
        },
        "pretty": {
            "type": "bool",
            "description": "Control pretty diagnostic output.",
        },
        "incremental": {
            "type": "bool",
            "description": "Enable incremental build information.",
        },
        "watch": {
            "type": "bool",
            "description": "Run tsc in watch mode.",
        },
        "skip-lib-check": {
            "type": "bool",
            "description": "Skip type checking of declaration files.",
        },
        "strict": {
            "type": "bool",
            "description": "Enable all strict type-checking options.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional compiler arguments appended to tsc.",
        },
    },
    "golangci-lint": {
        "config": {
            "type": "path",
            "description": "golangci-lint configuration file path.",
        },
        "deadline": {
            "type": "str",
            "description": "Timeout value passed to --deadline.",
        },
        "enable": {
            "type": "list[str]",
            "description": "Linters to enable explicitly.",
        },
        "disable": {
            "type": "list[str]",
            "description": "Linters to disable explicitly.",
        },
        "tests": {
            "type": "bool",
            "description": "Include tests in lint run.",
        },
        "issues-exit-code": {
            "type": "int",
            "description": "Custom exit code when issues are found.",
        },
        "build-tags": {
            "type": "list[str]",
            "description": "Go build tags supplied to the run.",
        },
        "skip-files": {
            "type": "list[str]",
            "description": "Regex patterns of files to skip.",
        },
        "skip-dirs": {
            "type": "list[str]",
            "description": "Regex patterns of directories to skip.",
        },
        "args": {
            "type": "list[str]",
            "description": "Additional arguments appended to golangci-lint run.",
        },
    },
}


def _build_field(spec: ToolSettingField) -> SettingField:
    enum = spec.get("enum")
    if isinstance(enum, list):
        enum_tuple = tuple(enum)
    elif isinstance(enum, tuple):
        enum_tuple = enum
    else:
        enum_tuple = None
    return SettingField(
        type=str(spec["type"]),
        description=str(spec["description"]),
        enum=enum_tuple,
    )


TOOL_SETTING_SCHEMA: ToolSettingSchema = {
    tool: {name: _build_field(spec) for name, spec in fields.items()}
    for tool, fields in RAW_TOOL_SETTING_SCHEMA.items()
}


def tool_setting_schema_as_dict() -> RawToolSettingSchema:
    """Return the original JSON-serialisable schema used for exports."""
    from copy import deepcopy

    return deepcopy(RAW_TOOL_SETTING_SCHEMA)


__all__ = ["TOOL_SETTING_SCHEMA", "SettingField", "tool_setting_schema_as_dict"]
