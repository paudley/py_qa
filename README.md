<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# PyQA Lint Orchestrator (`pyqa_lint`)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/pyqa_lint.svg)](https://pypi.org/project/pyqa_lint/)
[![Python Versions](https://img.shields.io/pypi/pyversions/pyqa_lint.svg)](https://pypi.org/project/pyqa_lint/)
[![CI](https://github.com/paudley/pyqa_lint/actions/workflows/ci.yml/badge.svg)](https://github.com/paudley/pyqa_lint/actions/workflows/ci.yml)
[![Release](https://github.com/paudley/pyqa_lint/actions/workflows/release.yml/badge.svg)](https://github.com/paudley/pyqa_lint/actions/workflows/release.yml)

PyQA is Blackcat Informatics Inc.'s opinionated quality-assurance harness. It ships as the `pyqa_lint` package (install via `pip install pyqa_lint`) and can also be vendored as a git submodule so teams can run the Typer-based CLI (`pyqa`) with zero external dependencies.

> **TL;DR**: Deterministic lint orchestration, SOLID-aware reporting, curated tool catalogs, and provenance-backed releases for modern Python repositories.

## Quick Links

* [Getting Started](#getting-started)
* [CLI Overview](#cli-overview)
* [Feature Highlights](#feature-highlights)
* [Architecture & Docs](#architecture--docs)
* [Releases & Provenance](#releases--provenance)
* [Configuration & Tooling Schema](#configuration--tooling-schema)
* [Advanced Capabilities](#advanced-capabilities)
* [Contributing & Support](#contributing--support)

## Table of Contents

1. [Why PyQA?](#why-pyqa)
2. [Installation Options](#installation-options)
3. [Getting Started](#getting-started)
4. [CLI Overview](#cli-overview)
5. [Feature Highlights](#feature-highlights)
6. [Architecture & Docs](#architecture--docs)
7. [Releases & Provenance](#releases--provenance)
8. [Configuration & Tooling Schema](#configuration--tooling-schema)
9. [Advanced Capabilities](#advanced-capabilities)
10. [Contributing & Support](#contributing--support)
11. [License](#license)

## Why PyQA?

* **Curated multi-language linting** powered by ruff, pylint, bandit, mypy, pyright, sqlfluff, yamllint, and more.
* **Polyglot coverage** across Python, JavaScript/TypeScript, Go, Rust, SQL, YAML, TOML, Markdown, Dockerfiles, Bash, and Lua via the built-in catalog.
* **Deterministic environments** built with `uv`, with optional system-tool reuse when explicitly allowed.
* **Explainable orchestration** via `--explain-tools` and `--explain-tools-json`, so contributors see why tools ran or skipped.
* **SOLID advice + refactor navigator** driven by tree-sitter and spaCy to highlight structural issues, hotspots, and symbols.
* **First-class reporting** to Markdown, SARIF 2.1.0, JSON, and PR summaries, plus machine-readable tool catalogs.
* **Interface-first design**: runtime modules consume Protocols from `pyqa.interfaces.*`, keeping extensions pluggable and testable.

## Language Coverage

PyQA's catalog bundles analyzers, formatters, and value-type rules for multiple ecosystems. Highlights include:

* **Python** – ruff, pylint, bandit, mypy, pyright, pytest helpers, value-type analysis.
* **JavaScript / TypeScript** – eslint, prettier, tsc, markdownlint cross-checks for front-end code.
* **Go** – golangci-lint, gofmt, module tidy helpers.
* **Rust** – clippy, cargo fmt, cargo check integrations.
* **Shell & Containers** – shellcheck, shfmt, hadolint, dockerfilelint.
* **Data & Config** – sqlfluff (SQL), yamllint (YAML), taplo (TOML), markdownlint/mdformat (Markdown), terraformer rules.
* **Scripting & DSLs** – luacheck (Lua), phpcs (PHP), generic tree-sitter hooks for custom DSLs.

Refer to `tooling/catalog/` for the authoritative list and metadata for each tool.

## Installation Options

### PyPI (recommended)

```bash
pip install pyqa_lint
# exposes the `pyqa` CLI globally
```

### Git Submodule

```bash
git submodule add https://github.com/paudley/pyqa_lint.git pyqa-lint
```

This layout keeps the managed scripts (`lint`, `check-quality`, `security-scan`, `install`, `install-hooks`, etc.) inside your repository without publishing a wheel.

### Local Development

Clone the repo and sync the toolchain:

```bash
uv sync --group dev
```

The shims in the repo root (`./lint`, `./check-quality`, `./install`, `./security-scan`) automatically target the synced `.venv`.

## Getting Started

1. `git submodule add https://github.com/paudley/pyqa_lint.git pyqa-lint`
2. `cd pyqa-lint && uv sync --group dev`
3. `./install-hooks` to wire `pre-commit`, `pre-push`, and `commit-msg`
4. `./lint` (or `pyqa lint`) to run the curated pipeline

Hooks and CI both execute `pyqa check-quality` + `pyqa lint`, so the same guardrails apply everywhere.

## CLI Overview

| Command         | How to run                                | Summary                                                                                   |
| --------------- | ----------------------------------------- | ----------------------------------------------------------------------------------------- |
| `lint`          | `pyqa lint` or `./lint`                   | Runs the orchestrated lint/test pipeline, explain mode, exporters, and cache management.  |
| `check-quality` | `pyqa check-quality` or `./check-quality` | Enforces SPDX headers, notices, schema freshness, file-size limits, and repo guardrails.  |
| `security-scan` | `pyqa security-scan` or `./security-scan` | Performs secret scanning plus Bandit/semgrep-style analyzers.                             |
| `install`       | `pyqa install` or `./install`             | Installs the managed toolchain into the current project (legacy shell workflow parity).   |
| `install-hooks` | `pyqa install-hooks` or `./install-hooks` | Symlinks vetted Git hooks that call `pyqa check-quality`.                                 |
| `config ...`    | `pyqa config <subcommand>`                | Show/diff/validate layered configuration, export tool schemas, inspect explainable plans. |
| `update`        | `pyqa update` or `./update-packages`      | Refresh pinned dependencies across Python/Node/Go/Rust workspaces.                        |
| `sparkly-clean` | `./sparkly-clean`                         | Remove caches and artefacts without touching tracked files.                               |

Run `pyqa --help` or `pyqa <command> --help` for detailed options.

## Feature Highlights

* **Explainable selection**: `pyqa lint --explain-tools [--json]` renders the tool order, reasons, eligibility, and registry descriptions. Tests assert table + JSON output so UX changes stay stable.
* **SOLID advice + highlighting**: `--advice` adds the SOLID panel, Refactor Navigator stats, and tree-sitter/spaCy highlighting. Exporters can embed the same data via `pyqa.reporting.emitters.write_pr_summary(include_advice=True)`.
* **Value-type analysis**: opt into `[tool.pyqa.generic_value_types]` in `pyproject.toml` and run `pyqa lint --check-value-types-general` to enforce structural traits (for example repositories must implement `__len__` + `__contains__`).
* **Deterministic envs**: `uv` manages every dependency. PyQA reuses system binaries only when they are newer and you have not forced `--use-local-linters`.
* **Rich reporting**: emit Markdown, SARIF, JSON, or PR summaries, and pipe catalogs into `ref_docs/tool-schema.json` with `pyqa config export-tools`.
* **Typed catalog + DI seams**: runtime modules only import from `pyqa.interfaces.*`, while the reusable schema lives in `src/tooling_spec/` for downstream consumers.

## Architecture & Docs

The REORG initiative is complete and all guidance now lives in first-class docs:

* `docs/ARCHITECTURE.md` – package responsibilities, SOLID guardrails, and interface boundaries.
* `SELECTION.md`, `SOLID_CLI.md`, `docs/orchestration/*` – orchestration internals, DI seams, progress rendering, and state machines.
* `docs/tooling/` – catalog schemas, shared knobs, and authoring guides.
* `docs/release/0.3.0.md` – highlights for the rename + provenance work.

Key takeaways:

* `pyqa.cache` handles persistence and cache repositories behind `pyqa.interfaces.cache`.
* `pyqa.analysis` provides spaCy/tree-sitter integrations and refactor analytics.
* `pyqa.reporting` owns console/Markdown/SARIF emitters and the SOLID advice builder.
* `pyqa.cli` hosts the Typer app, option builders, and launcher shims (mirrored by `./lint`, `./install`, etc.).
* `pyqa.tools` defines built-in tool registrations plus parser Protocols.
* `tooling_spec` is a standalone distribution exporting the catalog schema for external tooling.

## Releases & Provenance

* Package name: `pyqa_lint`; CLI/import namespace: `pyqa`.
* `v*` tags trigger `.github/workflows/release.yml`, which:
  1. Runs `uv sync --group dev`
  2. Builds sdist + wheel via `python -m build`
  3. Uploads artefacts for inspection
  4. Generates a GitHub attestation (`actions/attest-build-provenance@v1`)
  5. Publishes to PyPI via `pypa/gh-action-pypi-publish` with attestations enabled
* Required repo secret: `PYPI_API_TOKEN` (trusted publisher token for `pyqa_lint`).
* Release checklist: bump `pyproject.toml`, update `docs/release/<version>.md`, regenerate `ref_docs/tool-schema.json` (`uv run pyqa config export-tools --check ref_docs/tool-schema.json`), commit, tag `vX.Y.Z`, push tag.

## Configuration & Tooling Schema

* **Layered configuration**: defaults → `~/.pyqa_lint.toml` → `[tool.pyqa]` in `pyproject.toml` → `<project>/.pyqa_lint.toml`. Inspect with `pyqa config show --root <path> --trace` or compare layers via `pyqa config diff`.
* **Strict validation**: pass `--strict-config` (or `pyqa config validate --strict`) to fail on unknown keys.
* **License policy**: `[tool.pyqa.license]` declares SPDX identifiers, notices, year ranges, and exceptions enforced by `pyqa check-quality`.
* **Quality defaults**: `[tool.pyqa.quality]` centralizes enabled checks, schema targets, skip globs, and protected branches for hooks/CI.
* **Shared knobs**: `[complexity]` and `[strictness]` propagate limits to ruff, pylint, luacheck, mypy, pyright, tsc, etc. Sensitivity presets (`--sensitivity low|medium|high|maximum`) shift multiple thresholds together.
* **Tool overrides**: configure `[tool.pyqa.<tool>]` (or `.pyqa_lint.toml`'s `[tools.<tool>]`) to customize args/env per tool; CLI flags still win for ad-hoc overrides.
* **Schema exports**: `pyqa config schema --format markdown` documents every option; `pyqa config schema --format json-tools --out ref_docs/tool-schema.json` and `pyqa config export-tools` keep the checked-in schema current.

## Advanced Capabilities

### Value-Type Analyzer

```toml
[tool.pyqa.generic_value_types]
enabled = true

[[tool.pyqa.generic_value_types.rules]]
pattern = "myapp.repositories.*"
traits = ["iterable", "value"]
require = ["__len__", "__contains__"]
recommend = ["__repr__"]

[[tool.pyqa.generic_value_types.implications]]
trigger = "method:__len__"
require = ["__bool__"]
severity = "warning"
```

Run `pyqa lint --check-value-types-general` (or `./lint --check-value-types-general`). Diagnostics such as `generic-value-types:missing-required` demand a `suppression_valid` justification when they cannot be satisfied.

### Tooling Schema Validation

```bash
./lint --validate-schema
# or
uv run python -m jsonschema -F errors \
  -i tooling/catalog/languages/python/bandit.json \
  tooling/schema/tool_definition.schema.json
```

The catalog schemas are intentionally reusable so other orchestrators can adopt the same contracts. See `tooling/schema/SCHEMA.md` and `tooling/catalog/docs/SHARED_KNOBS.md` for field-by-field detail.

### NLP Requirements

Tree-sitter grammars are pinned in `pyproject.toml` and installed via `uv`. Install spaCy's English model once per environment:

```bash
uv run python -m spacy download en_core_web_sm
```

Override with `PYQA_NLP_MODEL=<model>` or disable highlighting entirely with `--no-color` in strict CI logs.

## Contributing & Support

* Review [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md) before submitting PRs.
* Run `uv run pyqa check-quality` and `uv run pytest` locally prior to opening a PR.
* File issues or feature requests directly on GitHub; include the output from `pyqa lint --explain-tools` when reporting orchestration bugs.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
