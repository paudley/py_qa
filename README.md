# Python Quality Assurance Scripting Submodule

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository provides a comprehensive suite of quality assurance, linting, testing, and utility scripts for modern Python projects. It is designed to be included as a git submodule (e.g., in a `scripts/` directory) to provide a standardized, battle-tested scripting environment.

## ✨ Features

-   **🤖 Automated Code Quality**: Enforce consistent code style, formatting, and best practices across your project.
-   **🚀 Comprehensive Linting**: Utilizes a powerful stack (`ruff`, `mypy`, `pylint`, `bandit`) to catch errors, bugs, and security issues early.
-   **📦 Dependency Management**: Scripts are self-contained and manage their Python environment using `uv`, ensuring consistent execution without polluting the parent project's venv.
-   **🔧 AI-Assisted Testing**: Includes scripts to leverage large language models (like Claude) to fix and enhance your `pytest` suite.
-   **🔒 Security Scanning**: Built-in secret and vulnerability scanning to keep your codebase secure.
-   **🛡️ Git Hooks**: Includes `pre-commit`, `pre-push`, and `commit-msg` hooks to automate quality checks.

##  Scripts Overview

### Core Quality & CI Scripts

-   **`lint.sh`**: The main linter orchestrator. Runs a full suite of formatters, type checkers, and linters. It's highly configurable and acts as the single source of truth for code quality.
-   **`check-quality.sh`**: Performs repository-level checks, such as validating license headers, checking for oversized files, and other project best practices.
-   **`security-scan.sh`**: Scans for hardcoded secrets, API keys, and other sensitive credentials in your staged files.
-   **`install-hooks.sh`**: Sets up Git hooks (`pre-commit`, `pre-push`, `commit-msg`) that automatically run the quality scripts, enforcing standards for every contributor.

### AI-Enhanced Testing

-   **`claude_test.sh`**: An AI-driven script that can automatically fix failing `pytest` tests or enhance an existing test suite for better coverage and robustness.
-   **`claude_test_all.sh`**: A wrapper to run `claude_test.sh` across multiple specified directories.
-   **`claude_lint.sh`**: An experimental script to automatically fix linting errors using an AI model.

### Reference Documentation

-   **`ref_docs/`**: A directory containing curated, in-depth technical guides on key technologies and architectural principles (SOLID, Pydantic, Polars, etc.). These documents are used to provide context to AI development assistants.

### Utility & Management Scripts

-   **`update_packages.sh`**: A convenience script to update all Python dependencies in `pyproject.toml` files using `uv`.
-   **`pre_run_clean.sh`**: Cleans the project directory of temporary files, caches, and build artifacts.
-   **`gen_aider_list.sh`**: Generates a file list for the `aider` AI coding assistant, pre-populating its context with relevant project files.

### Patches

-   **`pyreadstat_patch/`**: Contains a set of scripts to patch the `pyreadstat` library to handle non-UTF8 encoding in SPSS `.sav` files—a common real-world data science issue.

## 🚀 Quickstart: Integrating into Your Project

1.  **Add as a Submodule**: In your project's root directory, add this repository as a submodule. A common location is `py-qa/`.

    ```bash
    git submodule add https://github.com/your-username/qa-py.git qa-py
    ```

2.  **Install Git Hooks**: Run the installation script to set up the automated quality checks.

    ```bash
    ./py-qa/install-hooks.sh
    ```

3.  **Run a Full Lint Check**: Manually trigger a lint run to check your existing codebase.

    ```bash
    ./py-qa/lint.sh
    ```

Now, the Git hooks will automatically run on your commits and pushes, ensuring all new code meets the defined quality standards.

## ⚙️ Configuration

-   **Linting Rules**: Most tool configurations (ruff, mypy, pylint) are managed in `pyproject.toml`. You can fork this repository and adjust them to fit your project's needs.
-   **Banned Words**: Create a `.banned-words` file in your project root to add custom words or phrases that should be blocked from commit messages (e.g., internal project codenames).

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
