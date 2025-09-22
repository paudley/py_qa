# py-qa Refactoring Plan

## Objectives

- Decompose `lint.py` into a maintainable `pyqa` package under `src/` aligned with SOLID principles.
- Expose a Typer-powered CLI that will replace the monolithic script while preserving existing behaviour.
- Establish abstractions and dependency inversion boundaries to support pluggable linters, discovery strategies, and report pipelines.
- Modernize project configuration (pyproject, docs, tooling) for distribution via PyPI and consumption as a submodule.

## Guiding Design Principles

- **Single Responsibility**: Each module focuses on one concern (configuration, discovery, tooling, execution, reporting, CLI).
- **Open/Closed**: Adding new lint tools or discovery logic should be doable by implementing an interface and registering an adapter without editing core orchestration code.
- **Liskov & Interface Segregation**: Define narrow protocols (e.g. `FileDiscovery`, `ToolRunner`, `Reporter`, `Installer`) to avoid “fat” base classes.
- **Dependency Inversion**: High-level orchestration depends only on abstract protocols; concrete implementations are provided via factories/registries at runtime.
- **Testability**: Interfaces and functional decomposition should enable unit testing without invoking external binaries.

## Proposed Package Layout (`src/pyqa`)

```
pyqa/
  __init__.py               # Expose version, high-level API.
  cli.py                    # Typer app and entry point wiring.
  config.py                 # Dataclasses/pydantic models + loading/validation logic.
  logging.py                # User-facing logging utilities (color, emoji, formatting).
  discovery/
    __init__.py
    base.py                 # `WorkspaceDetector`, `FileDiscovery` protocols.
    git.py                  # Git-based discovery implementations.
    filesystem.py           # Glob and filesystem traversal helpers.
  tools/
    __init__.py
    base.py                 # `Tool`, `ToolInstaller`, `ToolRunner` protocols & shared helpers.
    registry.py             # Registration and lookup of tooling by name/language.
    builtins.py             # Concrete adapters for bundled tools (ported from lint.py).
  execution/
    __init__.py
    orchestrator.py         # High-level coordinator that wires discovery, tools, reporting.
    cache.py                # Caching primitives and hashing helpers.
    worker.py               # Threaded/async execution utilities.
  reporting/
    __init__.py
    formatters.py           # Pretty/raw/concise renderers.
    emitters.py             # JSON, SARIF, PR summary writers.
  installs.py               # Installer facade wrapping uv/pip behaviour.
  environments.py           # Environment preparation helpers (PATH, node env, etc.).
  severity.py               # Severity enums and rules handling.
```

`lint.py` will shrink to a thin shim that imports `pyqa.cli.app` and forwards `__main__` execution.

## Migration Steps

1. **Configuration Foundations**

   - Extract the existing dataclasses into `pyqa.config`. Replace argparse parsing with Typer commands that hydrate these models.
   - Introduce a `SettingsLoader` capable of sourcing defaults from files/env.

1. **Environment & Installation Utilities**

   - Move VENV/PATH manipulation helpers and installer logic into `pyqa.environments` and `pyqa.installs`.
   - Wrap subprocess execution behind interfaces that can be mocked/tested.

1. **Discovery Subsystem**

   - Port file discovery, git diff logic, and exclusion handling into `pyqa.discovery.*` modules.
   - Define `FileDiscovery` protocol returning iterables of candidate paths.

1. **Tool Abstractions**

   - Design `Tool` protocol encapsulating metadata, install requirements, and `run()`/`is_applicable()` behaviours.
   - Create registry for built-in tools. Migrate existing tool definitions from `lint.py` incrementally.

1. **Execution Orchestrator**

   - Implement an orchestrator class that ties together discovery results, tool registry, caching, threading, and output capture.
   - Ensure dependency inversion by accepting abstract `DiscoveryService`, `ToolRegistry`, and `Reporter` at construction.

1. **Reporting Layer**

   - Relocate output formatting, deduplication, SARIF/JSON writers into `pyqa.reporting` with composable formatters.
   - Separate concerns: data aggregation vs. rendering vs. persistence.

1. **CLI Integration**

   - Build Typer CLI commands in `pyqa.cli` to expose the orchestrator and configuration toggles.
   - Keep subcommands minimal initially (`lint`), but allow extension (e.g., `install`, `list-tools`).

1. **Shim & Backwards Compatibility**

   - Reduce `lint.py` to a bootstrapper (imports package CLI and calls it).
   - Provide console script entry point via `pyproject.toml`.

1. **Project Metadata & Tooling**

   - Update `pyproject.toml` with Typer dependency, uv best practices (e.g., `[tool.uv]`, dependency groups), and package metadata.
   - Configure `tool.ruff`, `tool.mypy`, etc., if appropriate.
   - Ensure ` uv.lock` is refreshed post dependency changes.

1. **Documentation & Examples**

   - Refresh README, add usage examples referencing the new CLI.
   - Document architecture in `ref_docs/` if needed.

1. **Testing & Quality**

   - Add minimal unit tests (e.g., config parsing, discovery) in `tests/` or ensure plan for future coverage.
   - Provide instructions in PLAN for future refactors of shell scripts to use Python equivalents.

## Dependencies to Introduce

- `typer>=0.12` (CLI handling).
- `rich>=13` (optional for better coloured output/logging; can be guarded fallback).
- Evaluate use of `pydantic` or `attrs` for configuration validation—include in implementation step if benefits outweigh cost.

## Tooling & Packaging Updates

- Configure `project.scripts = {"pyqa" = "pyqa.cli:app"}`.
- Adopt uv-native settings: leverage `[tool.uv]`, ensure optional dependency groups for linters.
- Document `.venv` workflow and uv commands in README.

## Documentation Deliverables

- This PLAN.md (checked in at repo root).
- README section describing new CLI usage, installation, package goals.
- Update any scripts/docs referencing `lint.py` to use `pyqa` CLI name.

## Open Questions / Follow-ups

- Confirm which external tools remain essential to port first vs. staged migration.
- Decide on persistence format for cached results (retain `.lint-cache` directory or redesign?).
- Determine testing strategy (unit vs. integration) once modularization is in place.
