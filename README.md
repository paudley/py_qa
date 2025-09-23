<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Python Quality Assurance Scripting Submodule

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository provides a comprehensive suite of quality assurance, linting, testing, and utility tooling for modern Python projects. It ships as a Python package (`pyqa`) with a Typer-based CLI and can also be included as a git submodule (e.g., in a `scripts/` directory) to provide a standardized, battle-tested scripting environment.

## ✨ Features

- **🤖 Automated Code Quality**: Enforce consistent code style, formatting, and best practices across your project.
- **🚀 Comprehensive Linting**: Utilizes a powerful stack (`ruff`, `mypy`, `pylint`, `bandit`, `sqlfluff`, `hadolint`, `yamllint`, `stylelint`, `actionlint`, `kube-linter`, `dotenv-linter`, `remark`, `selene`, `shfmt`, `golangci-lint`, `tombi`, and more) to catch errors, bugs, and security issues early via the modular `pyqa` orchestrator.
- **📦 Dependency Management**: Scripts are self-contained and manage their Python environment using `uv`, ensuring consistent execution without polluting the parent project's venv.
- **🧾 Typed Configuration**: Every configuration surface is backed by Pydantic models, delivering immediate validation, safer merges, and structured overrides across CLI, config files, and automation hooks.
- **🔌 Inversion-Friendly Design**: Core services (command preparation, discovery, reporting) follow explicit protocols, so teams can swap implementations or integrate with bespoke infrastructure without forking the toolchain.
- **🔧 AI-Assisted Testing**: Includes scripts to leverage large language models (like Claude) to fix and enhance your `pytest` suite.
- **🔒 Security Scanning**: Built-in secret and vulnerability scanning to keep your codebase secure.
- **🛡️ Git Hooks**: Includes `pre-commit`, `pre-push`, and `commit-msg` hooks to automate quality checks.
- **📄 Reporting Outputs**: Export machine-readable JSON, SARIF 2.1.0, and Markdown summaries for CI/CD and PR annotations.
- **🧰 Turnkey Install**: `pyqa install` mirrors the legacy shell workflow, installing dev dependencies, optional type stubs, and generated typing shims.
- **🛡️ Security Scan**: `pyqa security-scan` finds high-risk secrets/PII in your files (or staged changes) and runs Bandit for Python vulnerability checks.

## Scripts Overview

### Core Quality & CI Scripts

- **`lint`**: Primary Python-based lint orchestrator. Invoke `./py-qa/lint` from your project to run the complete suite without touching the host environment by default.
- **`check-quality`**: Runs repository-level quality enforcement including SPDX/license headers, copyright notices, file-size guardrails, schema verification, and Python hygiene.
- **`security-scan`**: Scans for hardcoded secrets, API keys, and other sensitive credentials in your staged files.
- **`install-hooks`**: PyQA CLI shim that symlinks the managed Git hooks (`pre-commit`, `pre-push`, `commit-msg`) into `.git/hooks`, ensuring quality checks run for every contributor.

### AI-Enhanced Testing

- **`claude_test.sh`**: An AI-driven script that can automatically fix failing `pytest` tests or enhance an existing test suite for better coverage and robustness.
- **`claude_test_all.sh`**: A wrapper to run `claude_test.sh` across multiple specified directories.
- **`claude_lint.sh`**: An experimental script to automatically fix linting errors using an AI model.

### Reference Documentation

- **`ref_docs/`**: A directory containing curated, in-depth technical guides on key technologies and architectural principles (SOLID, Pydantic, Polars, etc.). These documents are used to provide context to AI development assistants.

### Utility & Management Scripts

- **`update-packages`**: Python CLI shim for `pyqa update`, which scans the repository and refreshes dependencies for Python (uv), Node (npm/yarn/pnpm), Go modules, and Cargo workspaces in one pass.
- **`sparkly-clean`**: Wipes cache/coverage artefacts (`__pycache__`, `.venv`, logs, coverage files, dist/, etc.) while leaving real source changes intact—great before packaging or switching branches.
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
   ./py-qa/install-hooks
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
./py-qa/security-scan --no-bandit --no-staged ./path/to/file
./py-qa/check-quality --staged
uv run pyqa check-quality commit-msg .git/COMMIT_EDITMSG
uv run pyqa update --dry-run
```

Run `./py-qa/lint install` to install the preferred development dependencies, optional type stubs, and generated `stubgen` packages used by the workflow.

Additional quality-of-life flags mirror the original shell workflow:

- `--dir/--exclude` adjust discovery roots without touching the project root.
- `--filter TOOL:regex` trims noisy lines from individual tools (use `;;` to chain patterns).
- `--bail` exits on the first failing tool, while `--quiet` emits only failures.
- `--show-passing` together with `--verbose` matches traditional verbose summaries.
- `--use-local-linters` forces the vendored toolchain even when equal-or-newer system binaries are available.

### Environment Modes

- **Vendored by default** – running `./py-qa/lint` downloads linting toolchains into `py-qa/.lint-cache/tools` via `uv`/`npx` without modifying the host project. This is ideal when you want linting with zero impact on your repository or virtual environment.
- **Project-integrated** – `./py-qa/lint install` adds the recommended linters, stubs, and helpers directly to your project (and records the state so future runs prefer project tools). Editors and other tooling in the repo will see the installed packages automatically.
- **System toolchains** – when a compatible system binary is detected (and you have not forced local linters), pyqa will use it. Pass `--use-local-linters` to ignore system versions and rely on the vendored cache instead.

`./py-qa/lint` is the primary entry point and can be invoked directly from your repository root or via project automation.

`pyqa check-quality` replaces the legacy shell script with a Typer-driven command that enforces SPDX headers, canonical license and copyright notices, schema freshness, file-size thresholds, and Python hygiene. Hooks and CI call the shim (`./py-qa/check-quality`), but you can invoke it directly with `uv run pyqa check-quality` or scope it to staged files via `./py-qa/check-quality --staged`.

## ⚙️ Configuration

- **Layered settings**: Runtime behaviour pulls from built-in defaults, `~/.py_qa.toml`, `[tool.pyqa]` within `pyproject.toml`, and finally `<PROJECT>/.py_qa.toml`. Every layer is validated by Pydantic, so type mismatches or malformed paths surface immediately. Paths, lists, and include directives resolve relative to the project root, and environment variables like `${HOME}` expand inside configuration values.
- **Strict validation**: pass `--strict-config` to `pyqa lint` (or `--strict` to `pyqa config show/validate`) to fail on unknown tool options instead of only warning.
- **Inspect & debug**: Run `pyqa config show --root <project>` to view the merged configuration. Add `--trace` (enabled by default) to see which source last touched each option, or `pyqa config validate` to confirm all files load without errors.
- **Schema reference**: `pyqa config schema` emits JSON or Markdown for every setting—including per-tool options—and `pyqa config schema --format json-tools [--out tool-schema.json]` prints (or writes) just the tool override catalogue. Use `pyqa config export-tools tool-schema.json` to produce the same artifact explicitly.
- **License policy**: `[tool.pyqa.license]` in `pyproject.toml` lets you declare the canonical SPDX identifier, notice text, year range, and per-directory exceptions that the quality checker enforces across the repository.
- **Quality defaults**: `[tool.pyqa.quality]` controls which checks run (`checks`), repository-wide skip globs, schema targets, file-size thresholds, and protected branches so CLI, hooks, and CI share one source of truth.
- **Layer diffing**: `pyqa config diff` highlights changes between layers (defaults, home, pyproject, project, auto), making it easy to spot which source introduces a given override.
- **Tool overrides**: Provide tool-specific tables under `[tool.pyqa.bandit]` in `pyproject.toml` or `[tools.bandit]` in `.py_qa.toml` to fine-tune individual linters. Each section understands common keys (for example, `line-length`, `target-version`, `severity`), an `args` list to append arbitrary flags, and an `env` table merged into the tool process.
- **Linting Rules**: Tool-specific knobs (ruff, mypy, pylint) still respect their own config files (typically `pyproject.toml`). Customise them per project or fork this repo to adjust the baseline.
- **Banned Words**: Create a `.banned-words` file in your project root to add custom words or phrases that should be blocked from commit messages (e.g., internal project codenames).

## 🙌 Credits

PyQA stands on the shoulders of a generous open-source community. We’re especially grateful to the maintainers of:

- **Python-first linters & formatters**: [ruff](https://github.com/astral-sh/ruff), [ruff-format](https://github.com/astral-sh/ruff), [black](https://github.com/psf/black), [isort](https://github.com/PyCQA/isort), [mdformat](https://github.com/executablebooks/mdformat), [pylint](https://github.com/pylint-dev/pylint), [bandit](https://github.com/PyCQA/bandit), [pyupgrade](https://github.com/asottile/pyupgrade), and the [pydantic](https://github.com/pydantic/pydantic) team for powering our typed configuration story.
- **Polyglot coverage**: [sqlfluff](https://github.com/sqlfluff/sqlfluff), [yamllint](https://github.com/adrienverge/yamllint), [hadolint](https://github.com/hadolint/hadolint), [stylelint](https://github.com/stylelint/stylelint), [remark-lint](https://github.com/remarkjs/remark-lint), [dotenv-linter](https://github.com/wemake-services/dotenv-linter), [actionlint](https://github.com/rhysd/actionlint), [golangci-lint](https://github.com/golangci/golangci-lint), [kube-linter](https://github.com/stackrox/kube-linter), [shfmt](https://github.com/mvdan/sh), [tombi](https://github.com/kracejic/tombi), [gts](https://github.com/google/gts), [speccy](https://github.com/wework/speccy), [checkmake](https://github.com/mrtazz/checkmake), [cpplint](https://github.com/cpplint/cpplint), [selene](https://github.com/Kampfkarren/selene), [dockerfilelint](https://github.com/replicatedhq/dockerfilelint), [luacheck](https://github.com/mpeterv/luacheck), [lualint](https://github.com/philips/lualint), [perlcritic](https://github.com/Perl-Critic/Perl-Critic), [perltidy](https://github.com/perltidy/perltidy), [phplint](https://github.com/overtrue/phplint), [prettier](https://github.com/prettier/prettier), [tsc](https://github.com/microsoft/TypeScript), [gofmt](https://pkg.go.dev/cmd/gofmt), [cargo-clippy](https://github.com/rust-lang/rust-clippy), and [cargo-fmt](https://github.com/rust-lang/rustfmt) for making cross-language enforcement practical.
- **Static analysis & parsing**: [mypy](https://github.com/python/mypy), [pyright](https://github.com/microsoft/pyright), and the [tree-sitter](https://github.com/tree-sitter/tree-sitter) ecosystem (plus language bundles) which drive our language discovery and context enrichment.
- **Tooling infrastructure**: [uv](https://github.com/astral-sh/uv), [typer](https://github.com/tiangolo/typer), and the broader packaging community whose work keeps PyQA reproducible and approachable.

If PyQA streamlines your workflow, please consider supporting these upstream projects through sponsorships, bug reports, documentation improvements, or contributions.

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
