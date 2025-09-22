<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->
# Git Hooks

This directory contains Git hooks that enforce code quality standards.

## Installation

Run the installation script from the project root:

```bash
./py-qa/install-hooks.sh
```

This will install symlinks in `.git/hooks/` pointing to these templates.

## Hooks

### pre-commit

Runs before each commit to ensure code quality:

- **Formatting Check**: Ensures all Python files are properly formatted with `ruff format`
- **Linting**: Checks for code issues with `ruff check`
- **Type Checking**: Validates type annotations with `mypy` (source files only)
- **Debug Statements**: Prevents committing `print()` debug statements
- **TODO Check**: Blocks commits with `TODO BEFORE COMMIT` markers

### pre-push

Runs before pushing to ensure the codebase maintains high standards:

- **Full Lint Check**: Runs `./py-qa/lint` to ensure 10.00/10 Pylint score
- **Test Suite**: Runs all tests with pytest
- **Coverage Check**: Ensures comprehensive core functionality coverage is maintained

## Bypassing Hooks

In emergency situations, you can bypass hooks (not recommended):

```bash
# Skip pre-commit checks
git commit --no-verify

# Skip pre-push checks  
git push --no-verify
```

## Troubleshooting

### Virtual Environment Issues

The hooks automatically detect and activate the `.venv` virtual environment. If you see errors:

1. Ensure you have a virtual environment created: `uv venv`
1. Install dependencies: `uv pip sync pyproject.toml`

### Performance

The pre-push hook runs the full test suite and can take 30-60 seconds. This is intentional to ensure code quality before pushing.

## Customization

To modify hook behavior, edit the template files in this directory and re-run the installation script.
