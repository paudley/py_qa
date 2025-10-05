<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Python Typer CLI Blueprint

## Purpose

Describe the target architecture for fully integrating the `pyqa` command surface with Typer while respecting SOLID principles. This blueprint captures the conventions new commands must follow, the supporting infrastructure they rely on, and the seams that keep CLI bindings decoupled from orchestration logic.

## Entry Points & Application Wiring

* `pyqa.cli.app` owns the root `SortedTyper` instance. It registers standalone commands (`lint`, `install`, `security-scan`, `check-banned-words`) and sub-applications (`config`, `check-quality`, `update`, `sparkly-clean`, `install-hooks`).
* `pyqa.cli.typer_ext` defines `SortedTyperCommand`, `SortedTyperGroup`, and `create_typer()` to ensure deterministic option ordering and consistent help text styling across every command module.
* Repository scripts (`lint`, `sparkly-clean`, `check-banned-words`, `update-packages`, etc.) act as thin shims. They import the Typer app when installed locally, or fall back to `uv run pyqa <command>` to preserve backwards compatibility.
* `pyproject.toml` exposes the console script `pyqa = "pyqa.cli:app"`, allowing projects to depend on `pyqa` directly or invoke the bundled scripts without manipulating `PYTHONPATH`.

## Command Module Responsibilities

Each file under `pyqa/cli/` encapsulates one Typer command or command group.

* Input collection: declare `typer.Option`/`typer.Argument` bindings, enforce mutual exclusions, and normalise filesystem paths.
* Transformation: translate CLI primitives into typed request objects (for example, `LintOptions`), or dispatch to loader utilities (`ConfigLoader`, `build_config`).
* Delegation: invoke orchestration services (`Orchestrator`, `QualityChecker`, `WorkspaceUpdater`, `SecurityScanner`, etc.) that live outside the CLI package. Command modules never implement business logic directly.
* Presentation: emit user-facing output via `rich` helpers, logging adapters, and Typer exit codes. Domain services return structured results that CLI modules format.

This separation ensures that adding or modifying a command requires only CLI binding updates; orchestration components remain importable for use in other automation contexts.

## Shared Infrastructure

* `pyqa.cli.options` collects immutable dataclasses (e.g., `LintOptions`, `InstallOptions`) for passing structured data to the orchestrator layer.
* `pyqa.cli.config_builder` hydrates execution, discovery, and output configurations by merging CLI overrides with persisted settings. It centralises precedence rules and default filter construction.
* `pyqa.cli.utils` provides UV invocation helpers, package discovery, and tool status inspection used across multiple commands.
* `pyqa.cli.doctor` exposes diagnostics functionality that the CLI can trigger (`pyqa lint --doctor`) without entangling optional rich output with the core command implementation.

## SOLID Alignment Goals

* **Single Responsibility**: Each command module handles only CLI concerns; orchestration, configuration, and stateful operations reside in dedicated subpackages (`config_loader`, `quality`, `update`, `execution`).
* **Open/Closed**: New commands integrate by creating a module that conforms to the established pattern and registering it in `app.py`. Domain services expose extension points (registries, strategies) so new behaviour layers on via registration rather than modification.
* **Liskov Substitution**: Command callbacks return `None`/raise `typer.Exit` consistently, and rely on typed interfaces (`ToolRegistry`, `Workspace`) that can be substituted with test doubles.
* **Interface Segregation**: CLI modules depend on narrow abstractions (for example, `CommandRunner`, `SecurityScanner.run`) instead of monolithic god objects, minimising excess coupling.
* **Dependency Inversion**: High-level CLI entry points consume abstractions defined by orchestration packages; concrete implementations attach via factories (`build_default_discovery`, `initialize_registry`) at runtime.

## Maximal Integration Checklist

1. Every published script or automation hook routes through `pyqa.cli.app` and uses `create_typer()` helpers to maintain consistent help output.
2. Command callbacks surface only orchestration-level APIs. If new logic surfaces, extract it into a non-CLI module before binding options.
3. Shared flags (e.g., emoji toggles, root selection) use common utilities or dataclasses so behavioural changes remain centralised.
4. Tests exercise CLI behaviour through Typer's `CliRunner`, living alongside orchestration unit tests to prevent regressions.
5. Documentation references the Typer-centric workflow (`uv run pyqa <command>`) and highlights how to extend the CLI via new modules.

## Future Enhancements

* Introduce a first-class `pyqa.cli.main()` wrapper that can inject global options (verbosity, colour) before dispatching to subcommands.
* Capture cross-cutting CLI telemetry (timing, analytics) via Typer middleware-like callbacks without leaking into business logic.
* Expand configuration discovery helpers so staged files, stdin, and explicit path lists share consistent diagnostics across commands.
* Provide a template command module in `ref_docs/` demonstrating the preferred Typer patterns for contributors.

Adhering to this blueprint keeps the `pyqa` CLI approachable, testable, and extensible while continuing to leverage Typer's ergonomics.
