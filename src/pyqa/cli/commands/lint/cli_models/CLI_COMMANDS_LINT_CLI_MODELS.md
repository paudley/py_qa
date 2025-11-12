# SPDX-License-Identifier: MIT

# Copyright (c) 2025 Blackcat Informatics® Inc.

# Lint CLI Models Package

## Overview

The `pyqa.cli.commands.lint.cli_models` package encapsulates the Typer dependency
factories, option coercion helpers, and supporting types that power the
`pyqa lint` command. Functions are organised by responsibility (target
discovery, runtime wiring, output handling, and meta actions) so each module
remains focused and testable.

## DI Seams

Each dependency factory consumes protocol-based services exposed by the CLI
runtime package. Aggregator modules re-export the public entry points, allowing
callers to depend on the stable surface without importing private modules.

## Patterns

* Thin modules with single areas of responsibility reduce churn and keep
  Typer dependency graphs small.
* Helper functions return plain dictionaries or existing dataclasses to avoid
  leaking implementation types across package boundaries.

## Extension Points

Additional CLI parameters can be introduced by adding new dependency factories
and wiring them into the assembly helpers. Modules exported from
`cli_models.__init__` are treated as the official extension surface.
