<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Python Quality Assurance Scripting Submodule

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository provides a comprehensive suite of quality assurance, linting, testing, and utility tooling for modern Python projects. It ships as a Python package (`pyqa`) with a Typer-based CLI and can also be included as a git submodule (e.g., in a `scripts/` directory) to provide a standardized, battle-tested scripting environment.

## ✨ Features

* **🤖 Automated Code Quality**: Enforce consistent code style, formatting, and best practices across your project.
* **🚀 Comprehensive Linting**: Utilizes a powerful stack (`ruff`, `mypy`, `pylint`, `bandit`) to catch errors, bugs, and security issues early via the modular `pyqa` orchestrator.
* **📦 Dependency Management**: Scripts are self-contained and manage their Python environment using `uv`, ensuring consistent execution without polluting the parent project's venv.
* **🔧 AI-Assisted Testing**: Includes scripts to leverage large language models (like Claude) to fix and enhance your `pytest` suite.
* **🔒 Security Scanning**: Built-in secret and vulnerability scanning to keep your codebase secure.
* **🛡️ Git Hooks**: Includes `pre-commit`, `pre-push`, and `commit-msg` hooks to automate quality checks.
* **📄 Reporting Outputs**: Export machine-readable JSON, SARIF 2.1.0, and Markdown summaries for CI/CD and PR annotations.
* **🧰 Turnkey Install**: `pyqa install` mirrors the legacy shell workflow, installing dev dependencies, optional type stubs, and generated typing shims.
* **🛡️ Security Scan**: `pyqa security-scan` finds high-risk secrets/PII in your files (or staged changes) and runs Bandit for Python vulnerability checks.

## Scripts Overview

### Core Quality & CI Scripts

* **`lint`**: Primary Python-based lint orchestrator. Invoke `./py-qa/lint` from your project to run the complete suite without touching the host environment by default.
* **`check-quality`**: Runs repository-level quality enforcement including SPDX/license headers, copyright notices, file-size guardrails, schema verification, and Python hygiene.
* **`security-scan`**: Scans for hardcoded secrets, API keys, and other sensitive credentials in your staged files.
* **`install-hooks`**: PyQA CLI shim that symlinks the managed Git hooks (`pre-commit`, `pre-push`, `commit-msg`) into `.git/hooks`, ensuring quality checks run for every contributor.

### AI-Enhanced Testing

* **`claude_test.sh`**: An AI-driven script that can automatically fix failing `pytest` tests or enhance an existing test suite for better coverage and robustness.
* **`claude_test_all.sh`**: A wrapper to run `claude_test.sh` across multiple specified directories.
* **`claude_lint.sh`**: An experimental script to automatically fix linting errors using an AI model.

### Reference Documentation

* **`ref_docs/`**: A directory containing curated, in-depth technical guides on key technologies and architectural principles (SOLID, Pydantic, Polars, etc.). These documents are used to provide context to AI development assistants.

### Utility & Management Scripts

* **`update-packages`**: Python CLI shim for `pyqa update`, which scans the repository and refreshes dependencies for Python (uv), Node (npm/yarn/pnpm), Go modules, and Cargo workspaces in one pass.
* **`sparkly-clean`**: Wipes cache/coverage artefacts (`__pycache__`, `.venv`, logs, coverage files, dist/, etc.) while leaving real source changes intact—great before packaging or switching branches.
* **`pre_run_clean.sh`**: Cleans the project directory of temporary files, caches, and build artifacts.
* **`gen_aider_list.sh`**: Generates a file list for the `aider` AI coding assistant, pre-populating its context with relevant project files.

### Patches

* **`pyreadstat_patch/`**: Contains a set of scripts to patch the `pyreadstat` library to handle non-UTF8 encoding in SPSS `.sav` files—a common real-world data science issue.

## 🚀 Quickstart: Integrating into Your Project

1. **Add as a Submodule**: In your project's root directory, add this repository as a submodule. A common location is `py-qa/`.

   ```bash
   git submodule add https://github.com/paudley/qa-py.git qa-py
   ```

2. **Install Git Hooks**: Run the installation script to set up the automated quality checks.

   ```bash
   ./py-qa/install-hooks
   ```

3. **Bootstrap the Environment**: Install the managed dependencies into `.venv` using `uv`.

   ```bash
   cd py-qa
   uv sync --group dev
   ```

4. **Run a Full Lint Check**: Invoke the Typer CLI to lint your project.

   ```bash
   ./py-qa/lint
   ```

Now, the Git hooks will automatically run on your commits and pushes, ensuring all new code meets the defined quality standards.

## 🧰 CLI Usage

The new Typer application exposes a `lint` command with a modular configuration surface:

```bash
./py-qa/lint --help
./py-qa/lint path/to/file.py --dir src --exclude .venv
./py-qa/lint --changed-only --only ruff --only black --filter ruff:'^Found 0 errors'
./py-qa/lint --report-json reports/lint.json --sarif-out reports/lint.sarif
./py-qa/lint --jobs 8 --cache-dir .lint-cache --pr-summary-out reports/summary.md
./py-qa/lint --pr-summary-min-severity error --pr-summary-template "* [{severity}] {message}"
./py-qa/lint --bail --quiet
./py-qa/security-scan --no-bandit --no-staged ./path/to/file
./py-qa/check-quality --staged
uv run pyqa check-quality commit-msg .git/COMMIT_EDITMSG
uv run pyqa update --dry-run
```

Run `./py-qa/lint install` to install the preferred development dependencies, optional type stubs, and generated `stubgen` packages used by the workflow.

Additional quality-of-life flags mirror the original shell workflow:

* `--dir/--exclude` adjust discovery roots without touching the project root.
* `--filter TOOL:regex` trims noisy lines from individual tools (use `;;` to chain patterns).
* `--bail` exits on the first failing tool, while `--quiet` emits only failures.
* `--show-passing` together with `--verbose` matches traditional verbose summaries.
* `--use-local-linters` forces the vendored toolchain even when equal-or-newer system binaries are available.

### Environment Modes

* **Vendored by default** – running `./py-qa/lint` downloads linting toolchains into `py-qa/.lint-cache/tools` via `uv`/`npx` without modifying the host project. This is ideal when you want linting with zero impact on your repository or virtual environment.
* **Project-integrated** – `./py-qa/lint install` adds the recommended linters, stubs, and helpers directly to your project (and records the state so future runs prefer project tools). Editors and other tooling in the repo will see the installed packages automatically.
* **System toolchains** – when a compatible system binary is detected (and you have not forced local linters), pyqa will use it. Pass `--use-local-linters` to ignore system versions and rely on the vendored cache instead.

`./py-qa/lint` is the primary entry point and can be invoked directly from your repository root or via project automation.

`pyqa check-quality` replaces the legacy shell script with a Typer-driven command that enforces SPDX headers, canonical license and copyright notices, schema freshness, file-size thresholds, and Python hygiene. Hooks and CI call the shim (`./py-qa/check-quality`), but you can invoke it directly with `uv run pyqa check-quality` or scope it to staged files via `./py-qa/check-quality --staged`.

## ⚙️ Configuration

* **Layered settings**: Runtime behaviour pulls from built-in defaults, `~/.py_qa.toml`, `[tool.pyqa]` within `pyproject.toml`, and finally `<PROJECT>/.py_qa.toml`. Paths, lists, and include directives are resolved relative to the project root, and environment variables like `${HOME}` expand inside configuration values.

* **Strict validation**: pass `--strict-config` to `pyqa lint` (or `--strict` to `pyqa config show/validate`) to fail on unknown tool options instead of only warning.

* **Inspect & debug**: Run `pyqa config show --root <project>` to view the merged configuration. Add `--trace` (enabled by default) to see which source last touched each option, or `pyqa config validate` to confirm all files load without errors.

* **Schema reference**: `pyqa config schema` emits JSON or Markdown for every setting—including per-tool options—and `pyqa config schema --format json-tools [--out tool-schema.json]` prints (or writes) just the tool override catalogue. Use `pyqa config export-tools tool-schema.json` to produce the same artifact explicitly.

* **License policy**: `[tool.pyqa.license]` in `pyproject.toml` lets you declare the canonical SPDX identifier, notice text, year range, and per-directory exceptions that the quality checker enforces across the repository.

* **Quality defaults**: `[tool.pyqa.quality]` controls which checks run (`checks`), repository-wide skip globs, schema targets, file-size thresholds, and protected branches so CLI, hooks, and CI share one source of truth.

* **Layer diffing**: `pyqa config diff` highlights changes between layers (defaults, home, pyproject, project, auto), making it easy to spot which source introduces a given override.

* **Layer diffing**: `pyqa config diff` highlights changes between layers (defaults, home, pyproject, project, auto), making it easy to spot which source introduces a given override.

* **Shared complexity & strictness**: Set project-wide thresholds once under `[complexity]` (e.g. `max_complexity`, `max_arguments`) and `[strictness]` (`type_checking = "lenient" | "standard" | "strict"`). PyQA synchronises these values across `pylint`, `luacheck`, `mypy`, `pyright`, `tsc`, `ruff`, `prettier`, and other hosted linters so you don’t fight conflicting warnings. See `ref_docs/tool_help/SHARED_KNOBS.md` for the full mapping and additional shared severity knobs.

* **Sensitivity presets**: Dial `--sensitivity (low|medium|high|maximum)` or set `[severity] sensitivity` to shift multiple knobs together. Low loosens limits (line length 140, complexity 15/7, lenient typing, Bandit low CONF/SEV, pylint fail-under 8.0, allows 200 warnings). Medium restores the defaults (line length 120, complexity 10/5, strict typing, Bandit medium, fail-under 9.5, clears warning caps). High drops limits (line length 110, complexity 8/4, strict typing, Bandit high, fail-under 9.75, max warnings 5). Maximum is the strictest profile (line length 100, complexity 6/3, Bandit high, fail-under 9.9, max warnings 0). CLI overrides like `--line-length` or `--max-complexity` still win when provided.

* *Example*:

  ```toml
  [complexity]
  max_complexity = 12
  max_arguments = 6

  [strictness]
  type_checking = "standard"
  ```

* **Tool overrides**: Provide tool-specific tables under `[tool.pyqa.bandit]` in `pyproject.toml` or `[tools.bandit]` in `.py_qa.toml` to fine-tune individual linters. Each section understands common keys (for example, `line-length`, `target-version`, `severity`), an `args` list to append arbitrary flags, and an `env` table merged into the tool process. Global settings like `execution.line_length` and `[complexity]` cascade automatically; override them per-tool only when deviating from the shared defaults.

* **Linting Rules**: Tool-specific knobs (ruff, mypy, pylint) still respect their own config files (typically `pyproject.toml`). Customise them per project or fork this repo to adjust the baseline.

* **Banned Words**: Create a `.banned-words` file in your project root to add custom words or phrases that should be blocked from commit messages (e.g., internal project codenames).

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
