# Python Quality Assurance Scripting Submodule

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository provides a comprehensive suite of quality assurance, linting, testing, and utility tooling for modern Python projects. It ships as a Python package (`pyqa`) with a Typer-based CLI and can also be included as a git submodule (e.g., in a `scripts/` directory) to provide a standardized, battle-tested scripting environment.

## ✨ Features

- **🤖 Automated Code Quality**: Enforce consistent code style, formatting, and best practices across your project.
- **🚀 Comprehensive Linting**: Utilizes a powerful stack (`ruff`, `mypy`, `pylint`, `bandit`) to catch errors, bugs, and security issues early via the modular `pyqa` orchestrator.
- **📦 Dependency Management**: Scripts are self-contained and manage their Python environment using `uv`, ensuring consistent execution without polluting the parent project's venv.
- **🔧 AI-Assisted Testing**: Includes scripts to leverage large language models (like Claude) to fix and enhance your `pytest` suite.
- **🔒 Security Scanning**: Built-in secret and vulnerability scanning to keep your codebase secure.
- **🛡️ Git Hooks**: Includes `pre-commit`, `pre-push`, and `commit-msg` hooks to automate quality checks.
- **📄 Reporting Outputs**: Export machine-readable JSON, SARIF 2.1.0, and Markdown summaries for CI/CD and PR annotations.
- **🧰 Turnkey Install**: `pyqa install` mirrors the legacy shell workflow, installing dev dependencies, optional type stubs, and generated typing shims.

## Scripts Overview

### Core Quality & CI Scripts

- **`lint`**: The main linter orchestrator implemented in Python. Run `./py-qa/lint` to execute a full suite of formatters, type checkers, and linters.
- **`lint`**: Primary Python-based lint orchestrator. Invoke `./py-qa/lint` from your project to run the complete suite without touching the host environment by default.
- **`check-quality.sh`**: Performs repository-level checks, such as validating license headers, checking for oversized files, and other project best practices.
- **`security-scan.sh`**: Scans for hardcoded secrets, API keys, and other sensitive credentials in your staged files.
- **`install-hooks.sh`**: Sets up Git hooks (`pre-commit`, `pre-push`, `commit-msg`) that automatically run the quality scripts, enforcing standards for every contributor.

### AI-Enhanced Testing

- **`claude_test.sh`**: An AI-driven script that can automatically fix failing `pytest` tests or enhance an existing test suite for better coverage and robustness.
- **`claude_test_all.sh`**: A wrapper to run `claude_test.sh` across multiple specified directories.
- **`claude_lint.sh`**: An experimental script to automatically fix linting errors using an AI model.

### Reference Documentation

- **`ref_docs/`**: A directory containing curated, in-depth technical guides on key technologies and architectural principles (SOLID, Pydantic, Polars, etc.). These documents are used to provide context to AI development assistants.

### Utility & Management Scripts

- **`update_packages.sh`**: A convenience script to update all Python dependencies in `pyproject.toml` files using `uv`.
- **`pre_run_clean.sh`**: Cleans the project directory of temporary files, caches, and build artifacts.
- **`gen_aider_list.sh`**: Generates a file list for the `aider` AI coding assistant, pre-populating its context with relevant project files.

### Patches

- **`pyreadstat_patch/`**: Contains a set of scripts to patch the `pyreadstat` library to handle non-UTF8 encoding in SPSS `.sav` files—a common real-world data science issue.

## 🚀 Quickstart: Integrating into Your Project

1. **Add as a Submodule**: In your project's root directory, add this repository as a submodule. A common location is `py-qa/`.

   ```bash
   git submodule add https://github.com/paudley/qa-py.git qa-py
   ```

1. **Install Git Hooks**: Run the installation script to set up the automated quality checks.

   ```bash
   ./py-qa/install-hooks.sh
   ```

1. **Bootstrap the Environment**: Install the managed dependencies into `.venv` using `uv`.

   ```bash
   cd py-qa
   uv sync --group dev
   ```

1. **Run a Full Lint Check**: Invoke the Typer CLI to lint your project.

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
```

Run `./py-qa/lint install` to install the preferred development dependencies, optional type stubs, and generated `stubgen` packages used by the workflow.

Additional quality-of-life flags mirror the original shell workflow:

- `--dir/--exclude` adjust discovery roots without touching the project root.
- `--filter TOOL:regex` trims noisy lines from individual tools (use `;;` to chain patterns).
- `--bail` exits on the first failing tool, while `--quiet` emits only failures.
- `--show-passing` together with `--verbose` matches traditional verbose summaries.
- `--use-local-linters` forces the vendored toolchain even when equal-or-newer system binaries are available.

### Environment Modes

- **Vendored by default** – running `./py-qa/lint` downloads linting toolchains into `py-qa/.tool-cache` via `uv`/`npx` without modifying the host project. This is ideal when you want linting with zero impact on your repository or virtual environment.
- **Project-integrated** – `./py-qa/lint install` adds the recommended linters, stubs, and helpers directly to your project (and records the state so future runs prefer project tools). Editors and other tooling in the repo will see the installed packages automatically.
- **System toolchains** – when a compatible system binary is detected (and you have not forced local linters), pyqa will use it. Pass `--use-local-linters` to ignore system versions and rely on the vendored cache instead.

`./py-qa/lint` is the primary entry point and can be invoked directly from your repository root or via project automation.

## ⚙️ Configuration

- **Linting Rules**: Most tool configurations (ruff, mypy, pylint) are managed in `pyproject.toml`. You can fork this repository and adjust them to fit your project's needs.
- **Banned Words**: Create a `.banned-words` file in your project root to add custom words or phrases that should be blocked from commit messages (e.g., internal project codenames).

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
