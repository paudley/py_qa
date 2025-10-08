# pyqa.cli Module Guide

## Overview

`pyqa.cli` hosts the public command-line interface for pyqa. It wires Typer
commands to orchestrator pipelines via dependency injection and exposes
entry-point seams for plugins to register additional commands.

## Responsibilities

* Parse CLI arguments into `PreparedLintState` and configuration models.
* Delegate orchestration to `pyqa.orchestration` through interface-driven
  adapters.
* Produce user-facing output (console, reports, artifacts) without embedding
  business logic.
* Register built-in commands (lint, clean, install-hooks, quality, etc.) while
  deferring implementation specifics to feature packages.

## Dependency Injection Seams

* Commands resolve collaborators from `ServiceContainer` instances seeded in
  `cli/core/runtime.py`.
* Annotation, reporting, and discovery services must be requested through
  interfaces (`pyqa.interfaces.*`), never by importing concretes directly.
* Composition roots live in `cli/core/orchestration.py` and
  `cli/commands/*/runtime.py`; other modules consume interfaces only.

## Extension Points

* Plugin authors can register Typer applications via the
  `pyqa.cli.plugins` entry-point group and integrate by depending on exposed
  interfaces.
* New commands should follow the pattern in `cli/commands/{command}/` with
  dedicated `models.py`, `services.py`, and `runtime.py` modules.

## Patterns & Anti-Patterns

* **Do** keep command handlers thin; move orchestration into `runtime` helpers.
* **Do** use all shared logging helpers from `pyqa.core.logging` rather than
  creating ad-hoc consoles.
* **Do not** instantiate orchestrators or annotation engines directly; rely on
  DI helpers in `cli/core/`.
* **Do not** import feature modules (analysis/reporting/orchestration) without
  going through their interface counterparts.

## Testing Notes

* `tests/test_lint_cli.py` exercises meta-flag behaviours and report generation.
* Prefer CLI runner fixtures for integration tests to ensure command wiring
  stays SOLID-compliant.
