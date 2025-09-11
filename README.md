# Python Quality Assurance and Scripting Utilities

This repository contains a collection of quality assurance, testing, and utility scripts for Python projects. It is designed to be included as a git submodule to provide a standardized scripting environment.

## Scripts

### `run.py` (formerly `extract.py`) - Python Runner
A simple Python script to run the main CLI of the parent project. This should be adapted as the primary entrypoint.

```bash
# Make executable
chmod +x scripts/run.py

# Usage examples
./scripts/run.py --help
```

### `run.sh` (formerly `extract.sh`) - Bash Wrapper
A simple bash script that calls the Python module with proper environment setup.

```bash
# Make executable
chmod +x scripts/extract.sh

# Usage examples
./scripts/run.sh --help
./scripts/extract.sh extract gwp
./scripts/extract.sh extract gpss --comprehensive
bash scripts/extract.sh validate schema.json
```

## Core Scripts

This repository provides several core scripts for maintaining code quality:

-   `lint.sh`: Runs a comprehensive suite of linters and formatters (ruff, mypy, black, etc.).
-   `claude_test.sh`: An AI-driven script to automatically fix or enhance the pytest test suite.
-   `check-quality.sh`: Performs checks for license headers, file sizes, and common code quality issues.
-   `security-scan.sh`: Scans for hardcoded secrets and credentials.
-   `install-hooks.sh`: Installs git hooks that use the above scripts to enforce quality on commit and push.

## Environment Setup

The scripts manage their own environment to ensure consistency.

-   They use `uv` to create and manage a `.venv` virtual environment.
-   Dependencies are automatically installed and synced when scripts are run.
-   Path and environment validation is included.
