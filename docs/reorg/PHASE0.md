# Phase 0 – Reorg Readiness

This document captures the artefacts and decisions produced while executing
Phase 0 of the module reorganisation roadmap (`REORG_PLAN.md`).

## Outputs

* **Dependency graph** – generated via `reorg/scripts/generate_dependency_graph.py`
  and stored in `reorg/artifacts/phase0/pyqa_dependency_graph.json`. The graph
  lists every `pyqa` module with its direct intra-package imports plus a
  histogram of dependency counts.
* **Plugin scaffolding** – entry-point groups (`pyqa.catalog.plugins`,
  `pyqa.cli.plugins`, `pyqa.diagnostics.plugins`) are registered in
  `pyproject.toml`, and the new `pyqa.plugins` module exposes loaders that
  resolve those entry points.
* **Tests** – `tests/plugins/test_entry_points.py` validates loader behaviour
  across both dict-based and selector-based `importlib.metadata` APIs.
* **Module move inventory** – `reorg/artifacts/phase0/module_move_candidates.json`
  captures the initial source modules slated for each future package, serving as
  the baseline for Phase 1 refactors.
* **Architecture smoke test** – `tests/architecture/test_dependency_graph.py`
  regenerates the dependency graph and asserts that all edges stay within the
  `pyqa` package, providing a foundation for stronger import lints in later
  phases.

## Next Steps

1. Review the dependency graph to identify tightly coupled modules that need
   extra care during the upcoming refactors.
2. Wire the plugin loaders into future interface packages once they exist
   (Phase 1).
3. Extend CI in later phases to run the graph generator and fail if new
   cross-package dependencies violate the planned architecture.
4. Wire the pyright/type-check stage into CI now that the baseline is clean
   (see `src/pyqa/analysis/suppression.py`).
