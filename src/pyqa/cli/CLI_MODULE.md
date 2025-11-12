<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# CLI Module Guide

This guide documents the architecture, patterns, and best practices used across
`src/pyqa/cli`. It distils the SOLID recovery work and lessons learned while
refactoring the command-line entrypoints.

## Architecture Overview

* **Models vs Services vs Orchestration**: Each command module should expose
  structured input models (dataclasses or Typer dependencies), services that
  transform or enrich that data, and a thin orchestration function (Typer
  command) that wires everything together.
* **Shared Infrastructure**: Common behaviours live in `cli/core/shared.py`
  (logging adapter, CLIError, registration helpers) and `cli/core/typer_ext.py`
  (sorted Typer wrappers). Prefer using these helpers instead of duplicating
  behaviours.
* **Catalog-Driven Configuration**: Tool metadata, language-specific settings,
  and (planned) shebang/Tree-sitter configuration come from the JSON catalog in
  `tooling/catalog`. Avoid embedding language-specific logic directly in the CLI
  modules.

## Key Modules

* `commands/lint/`: Owns lint execution (input models, preparation, runtime,
  progress, reporting, metadata export).
* `commands/config/`: Provides configuration inspection utilities, including
  snapshot rendering, diffs, markdown output, and export helpers.
* `commands/quality/`: Implements repository quality enforcement and rendering
  services.
* `commands/tool_info/`: Renders catalog-driven tool metadata through presenters
  and advice helpers.

## Patterns & Best Practices

1. **Single Responsibility Principle (SRP)**

   * Keep Typer commands thin; push preparation and business logic into services.
   * Group related helpers into focused modules (`_lint_preparation`, `_lint_runtime`, etc.).

2. **Open/Closed Principle (OCP)**

   * Swapping or adding behaviours should be data-driven (e.g. catalog or config dataclasses) rather than editing orchestration logic.
   * Use factories or hooks for behaviours that may vary (progress controller, logging, runtime orchestrator).

3. **Liskov Substitution Principle (LSP)**

   * When using interfaces (e.g. discovery matchers, runtime dependencies), ensure any implementation works with existing orchestration.

4. **Interface Segregation Principle (ISP)**

   * Provide narrow helper interfaces (e.g. registration decorators) instead of dumping large utility functions.
   * Depend on precise dataclasses or DTOs instead of untyped mappings.

5. **Dependency Inversion Principle (DIP)**

   * Orchestration functions (`lint_command`, `config_show`, etc.) should depend on abstractions or simple factories, not concrete module-level singletons.
   * Lint runtime creation uses `build_lint_runtime_context` so tests can inject alternative orchestrators.

## Usage Tips

* **Typer Registration**: Use `command_decorator` / `register_command` and
  `callback_decorator` / `register_callback` to keep registration consistent and lazily import heavy dependencies.
* **Logging**: Always obtain a `CLILogger` via `build_cli_logger` so logging respects `--no-emoji`/`--no-color` flags.
* **Options Containers**: Prefer annotated dependencies that return dataclasses
  (e.g. `LintCLIInputs`, `QualityCLIOptions`) to keep type hints clear and limit the number of Typer parameters per function.
* **Laziness**: The package-level `app` export in `pyqa.cli` is resolved lazily to avoid `runpy` warnings. External users should continue importing `pyqa.cli.app` normally.
* **Backwards Compatibility**: `_build_config` now requires a pre-constructed `LintOptions` instance, avoiding the fragile keyword-based constructor that previously triggered lint errors.
* **Wrappers**: Root-level launchers (e.g. `./lint`, `./tool-info`) all delegate through `pyqa.cli.launcher.launch`, which handles interpreter selection, `PYTHONPATH`, and optional `uv` fallback.
* **Plugin Loading**: `register_commands` automatically invokes entry points declared under `pyqa.cli.plugins`, allowing third-party packages to append commands without modifying the core registry.
* **Wrapper troubleshooting**: When wrappers misbehave, enable `PYQA_WRAPPER_VERBOSE=1` to see interpreter detection, check `PYQA_PYTHON`/`PYQA_UV` overrides, and confirm `.lint-cache/uv` is writable for automatic downloads.
* **Wrapper failure modes**: A successful probe requires Python ≥3.12 and imports resolving under `src/`; otherwise the launcher falls back to `uv --project … run python -m pyqa.cli.app`. Propagated exit codes make it safe to rely on wrappers within CI.

## Anti-Patterns

* **Direct Registry/Orchestrator Construction**: Do not instantiate `Orchestrator`
  or tool registries directly inside commands. Use the runtime factory helpers so tests and future refactors remain resilient.
* **Inline Option Parsing**: Avoid manual parsing of `ctx.args` or raw `sys.argv`
  in commands; rely on Typer dependencies or dedicated services (e.g. `_collect_provided_flags`).
* **Suppression Comments**: The CLI package must not use lint-suppression comments (`# type: ignore`, `# noqa`) unless paired with a robust explanation and approval. Refactor instead.

## Future Enhancements

* **Shebang & Tree-sitter Catalog Integration**: Expand language definitions in
  the catalog (`SHEBANG.md`) to include shebang matchers and Tree-sitter grammar metadata, keeping discovery and context resolution data-driven.
* **Language-Level Defaults**: Consolidate per-language defaults (extensions,
  config files) into catalog language records to reduce repetition in tool definitions.
* **Testing**: Strengthen CLI integration tests to cover new dependency factories and meta-command flows, especially once shebang detection is catalog-driven.

## References

* [SOLID CLI Recovery Plan](../SOLID_CLI.md)
* [Shebang Detection Plan](../SHEBANG.md)
* `src/pyqa/cli/core/shared.py`, `src/pyqa/cli/core/typer_ext.py`
* `tooling/catalog/languages/`
