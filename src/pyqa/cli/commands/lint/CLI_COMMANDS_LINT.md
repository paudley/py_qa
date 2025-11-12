<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Cli Commands Lint

## Overview

This document describes the pyqa.cli.commands.lint module.

## Patterns

* `--show-valid-suppressions` surfaces INFO-level diagnostics for
  `suppression_valid:` comments so reviewers can confirm justifications without
  failing the run.
* `--check-pyqa-python-hygiene` enables the repository-specific hygiene linter
  that watches for `SystemExit`/`os._exit` shortcuts and stray `print` calls in
  production modules.

## DI Seams

Document dependency inversion touchpoints and service registration expectations.

## Extension Points

Outline supported extension seams and guidance for contributors.
