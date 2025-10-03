# SOLID CLI Recovery Plan

## Phase 1: Shared Infrastructure

- [x] Introduce `cli/shared.py` with:
  - [x] Common CLI error class (`CLIError`) encapsulating exit codes/messages.
  - [x] Logging adapters honoring emoji/no-color preferences.
  - [x] Helper for registering Typer commands with consistent metadata.
- [x] Update `clean`, `hooks`, `quality`, `tool_info`, `config_cmd`, `lint`, `security`, `banned`, `install`, and `update` to use shared utilities for logging/errors.
- [x] Ensure backward compatibility exports remain for external callers.
- [x] Add dedicated override service modules for lint configuration (severity, complexity, strictness).

## Phase 2: Config Builder Decomposition

- [x] Replace magic values in `config_builder` helpers with enums/Literal types or named constants (e.g. serial job count, summary literals).
- [x] Extract remaining config mutation helpers (file discovery/output/execution) fully into service modules.
- [x] Add dataclasses or structured containers for groups of related overrides.
- [x] Update docstrings and typing to reflect new structures across the builder helpers.

## Phase 3: Typer Entry Normalization

- [x] Adopt a uniform pattern for Typer app creation (consistent use of `create_typer` and callbacks/registrations).
- [x] Use the shared registration helper for all CLI modules to standardize help text and invocation style.
- [x] Ensure option definitions originate from single-source dataclasses/annotated types wherever feasible (lint, quality, clean, hooks, config, update, install, security, banned, tool-info).

## Phase 4: Lint Pipeline Refinement

- [x] Extract progress controller lifecycle management into dedicated service helpers.
- [x] Move reporting dispatch (`handle_reporting`, quality append) into orchestrated helpers that accept simple DTOs and inject the shared logger.
- [x] Harmonize lint logging/output handling with shared logging adapters across preparation/fetch/reporting.
- [x] Decompose meta-command handling into `_lint_meta.py`, covering early and runtime actions with testable helpers.

## Phase 5: Final Cleanup & Validation

- [x] Review all CLI modules for consistent SOLID layering (models → services → orchestration/execution).
- [x] Update module-level docstrings and export lists to match the new structure (e.g., include new Typer command wrappers).
- [x] Perform a final static type check / lint run (when allowed) covering the entire CLI package (`uv run pyright src/pyqa/cli`).

## Phase 6: Runtime & Helper Refinements

- [x] Introduce a dependency-invertible runtime builder for lint execution (factory abstraction instead of direct `Orchestrator` construction).
- [x] Extract configuration diff orchestration into a `_config_cmd_services` helper consumed by the CLI entrypoint.
- [x] Refresh documentation for `quality.main` to represent the new options container signature.
- [x] Expand shared registration helpers to expose decorator factories without immediate side effects, keeping them single-purpose.

## Phase 7: Wrapper Assurance _(in progress)_

- [x] Migrate every wrapper script to the shared `scripts/cli_launcher.launch` helper.
- [x] Prefer the repository virtual environment when probing interpreters before falling back to `uv`.
- [ ] Capture representative CLI invocations in automated checks once test execution constraints lift.
- [x] Extend `cli/CLI_MODULE.md` and developer docs with wrapper troubleshooting guidance.
- [x] Model launcher scenarios in follow-up tasks (e.g., missing `uv`, stale virtualenv) to keep cache handling robust.

## Outstanding Lint Follow-ups

- [x] Resolve ``__all__`` export mismatches in `src/pyqa/__init__.py` flagged by pylint/pyright.
- [x] Normalise magic value comparisons in `src/pyqa/analysis/suppression.py` and related helpers.
- [x] Continue decomposing long-running annotations helpers to eliminate broad ``try`` blocks and invalid constant names.
