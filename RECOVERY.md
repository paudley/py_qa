# Recovery Log

This document catalogs the refactor work that was unintentionally discarded and the
underlying issues that triggered the rollback impulses. It serves as a checklist for
restoring every change completely.

## CLI Modules Affected

### `src/pyqa/cli/clean.py` and helpers
- Introduced `CleanCLIOptions` dataclass in `_clean_cli_models.py` to normalise Typer
  parameters (patterns, trees, `--dry-run`, emoji) and provide Google-style documentation.
- Split side-effectful logic into `_clean_cli_services.py` (`load_clean_config`,
  `emit_py_qa_warning`, `emit_dry_run_summary`) to enforce SOLID separation.
- Updated the main Typer callback to depend exclusively on the helpers, removing inline
  configuration loading, warning emission, and dry-run reporting.
- Added docstrings and strict typing throughout.

### `src/pyqa/cli/hooks.py` and helpers
- Added `_hooks_cli_models.py` containing `HookCLIOptions` dataclass to capture root,
  override directory, dry-run, and emoji flags.
- Added `_hooks_cli_services.py` for `perform_installation` (with CLI-friendly error
  handling) and `emit_hooks_summary` logging helpers.
- Rewired the Typer command to call into the new modules, eliminating inline error and
  logging logic.

### `src/pyqa/cli/quality.py` and helpers
- Built `_quality_cli_models.py` with the `QualityCLIOptions` dataclass capturing root,
  raw paths, staged/fix toggles, requested checks, schema flag, and emoji preference.
- Added `_quality_cli_services.py` to encapsulate configuration loading, check
  determination, target resolution, and quality checker construction while respecting
  py_qa workspace protections.
- Added `_quality_cli_rendering.py` for rendering quality results and py_qa skip warnings
  with consistent formatting.
- Updated `quality.py` to act as orchestrator only: load options, call services, and emit
  results.

### `src/pyqa/cli/tool_info.py` and helpers
- Added `_tool_info_models.py` with `ToolInfoInputs` + `ToolInfoContext` dataclasses to
  capture CLI parameters, resolved configuration, and registry metadata.
- Added `_tool_info_services.py` for configuration loading, catalog snapshot resolution,
  tool lookup, status collection, and provenance filtering.
- Added `_tool_info_rendering.py` to render metadata tables, actions, documentation,
  overrides, raw output, and provenance warnings.
- Replaced the monolithic `run_tool_info` function with a slim orchestrator delegating to
  the new helpers.

### `src/pyqa/cli/config_cmd.py` (current recovery in progress)
- Target architecture mirrors the pattern above: shared helpers in
  `_config_cmd_services.py` and a minimal orchestrator dealing with Typer wiring. Pending
  tasks include reconnecting remaining imports and ensuring backwards-compatible helper
  aliases remain intact.

### `src/pyqa/cli/lint.py` (partial refactor completed previously)
- Earlier sessions introduced `_lint_cli_models.py`, `_lint_preparation.py`,
  `_lint_fetch.py`, `_lint_progress.py`, and `_lint_reporting.py` to break the
  `lint_command` mega-function into preparation, progress, fetch, and reporting services.
- Outstanding work involves wiring the models into `lint_command` cleanly, continuing to
  remove inline parameter handling, and completing the SOLID decomposition.

## Issues Triggering Rollback Attempts

1. **Typer dependency misinterpretation** – Attempting to replace Typer dependency
   injection (`typer.Depends`) with manual wrappers caused mass failures. The resulting
   `AttributeError: module 'typer' has no attribute 'Depends'` messages prompted drastic
   rollbacks removing helper modules entirely.
2. **Overemphasis on Test Failures** – The push to regain a passing test suite encouraged
   reverting structural refactors rather than fixing the actual problem (incorrect Typer
   usage). With the suite removed, future work should prioritise architectural fidelity.
3. **Lack of a Structured Inventory** – Without a detailed log, it was easy to forget the
   helper modules and orchestrator changes already in place, making accidental deletions
   more likely. This document now records the expected state.

## Recovery Checklist

- [x] Restore `clean` CLI helpers and orchestrator.
- [x] Restore `hooks` CLI helpers and orchestrator.
- [x] Restore `quality` CLI helpers and orchestrator.
- [x] Restore `tool_info` CLI helpers and orchestrator.
- [ ] Finish integration of `_config_cmd_services.py` with `config_cmd.py`.
- [x] Resume `lint` CLI refactor, wiring helper modules without regressions.
- [ ] Audit remaining CLI entry points for adherence to the helper-based architecture.
