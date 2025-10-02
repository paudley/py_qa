# SOLID CLI Recovery Plan

## Phase 1: Shared Infrastructure
- [ ] Introduce `cli/shared.py` with:
  - [ ] Common CLI error class (`CLIError`) encapsulating exit codes/messages.
  - [ ] Logging adapters honoring emoji/no-color preferences.
  - [ ] Helper for registering Typer commands with consistent metadata.
- [ ] Update `clean`, `hooks`, `quality`, `tool_info`, `config_cmd`, `lint` to use shared utilities for logging/errors.
- [ ] Ensure backward compatibility exports remain for external callers.

## Phase 2: Config Builder Decomposition
- [ ] Replace magic values in `config_builder` with enums/Literal types where appropriate (sensitivity, max_complexity, etc.).
- [ ] Extract config mutation helpers into dedicated service functions (e.g., `_apply_threshold_overrides`, `_apply_execution_overrides`).
- [ ] Add dataclasses or structured containers for groups of related overrides.
- [ ] Update docstrings and typing to reflect new structures.

## Phase 3: Typer Entry Normalization
- [ ] Adopt a uniform pattern for Typer app creation (consistent use of `create_typer` and callbacks).
- [ ] Use the shared registration helper for all CLI modules to standardize help text and invocation style.
- [ ] Ensure option definitions originate from single-source dataclasses/annotated types wherever feasible.

## Phase 4: Lint Pipeline Refinement
- [ ] Extract progress controller lifecycle management into a dedicated service.
- [ ] Move reporting dispatch (`handle_reporting`, quality append) into orchestrated helpers that accept simple DTOs.
- [ ] Harmonize lint logging/output handling with shared logging adapters.
- [ ] Revisit `_run_early_meta_actions` / `_dispatch_meta_commands` for further decomposition if necessary.

## Phase 5: Final Cleanup & Validation
- [ ] Review all CLI modules for consistent SOLID layering (models → services → orchestrator).
- [ ] Update module-level docstrings and export lists to match new structure.
- [ ] Perform a final static type check / lint (when allowed) to ensure integrity.
