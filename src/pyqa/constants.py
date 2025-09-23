# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared constants used across pyqa modules."""

from __future__ import annotations

from typing import Final

ALWAYS_EXCLUDE_DIRS: Final[set[str]] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "coverage",
    ".tool-cache",
    ".cache",
}

LANGUAGE_EXTENSIONS: Final[dict[str, set[str]]] = {
    "python": {".py", ".pyi"},
    "javascript": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"},
    "go": {".go"},
    "rust": {".rs"},
    "markdown": {".md", ".mdx", ".markdown"},
    "github-actions": {".yml", ".yaml"},
    "sql": {".sql"},
    "kubernetes": set(),
    "css": {".css", ".scss", ".sass", ".less"},
    "yaml": {".yml", ".yaml"},
    "docker": set(),
    "dotenv": set(),
    "lua": {".lua"},
    "openapi": set(),
}

LANGUAGE_MARKERS: Final[dict[str, set[str]]] = {
    "python": {
        "pyproject.toml",
        "setup.cfg",
        "requirements.txt",
        "pipfile",
        "poetry.lock",
    },
    "javascript": {
        "package.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "tsconfig.json",
    },
    "go": {"go.mod"},
    "rust": {"Cargo.toml"},
    "github-actions": {".github/workflows"},
    "kubernetes": {
        "kustomization.yaml",
        "kustomization.yml",
        "Chart.yaml",
        "helmfile.yaml",
        ".kube-linter.yaml",
        ".kube-linter.yml",
        "charts",
        "manifests",
    },
    "css": {
        ".stylelintrc",
        ".stylelintrc.json",
        ".stylelintrc.yaml",
        ".stylelintrc.yml",
        ".stylelintrc.js",
        "stylelint.config.js",
        "stylelint.config.cjs",
        "stylelint.config.mjs",
        "stylelint.config.ts",
        "stylelint.config.coffee",
    },
    "yaml": {
        ".yamllint",
        ".yamllint.yaml",
        ".yamllint.yml",
        "yamllint.yaml",
        "yamllint.yml",
    },
    "docker": {
        "Dockerfile",
        "dockerfile",
        "Containerfile",
    },
    "dotenv": {
        ".env",
        ".env.example",
        ".env.template",
    },
    "lua": {
        ".luacheckrc",
        "init.lua",
    },
    "openapi": {
        "openapi.yaml",
        "openapi.yml",
        "swagger.yaml",
        "swagger.yml",
        "speccy.yaml",
        "speccy.yml",
    },
}

LANGUAGE_FILENAMES: Final[dict[str, set[str]]] = {
    "docker": {"dockerfile", "containerfile"},
    "dotenv": {".env", "env"},
    "lua": {"init.lua"},
    "openapi": {"openapi.yaml", "openapi.yml", "swagger.yaml", "swagger.yml", "speccy.yaml", "speccy.yml"},
}
