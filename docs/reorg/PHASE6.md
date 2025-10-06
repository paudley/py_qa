<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Phase 6 – Hardening & Release Checklist

Phase 6 finalises the module reorganisation by polishing the documentation,
verifying architectural guardrails, and outlining the release ceremony for both
runtime and specification packages.

## 📚 Documentation Updates

* README now documents the dual-package layout (`pyqa`, `tooling_spec`) and the
  requirement that spaCy (including `en_core_web_sm`) and the tree-sitter
  grammars are present at runtime.
* CLI guidance references the reorganised packages (`pyqa.reporting.advice` →
  `pyqa.reporting.advice.builder`) and removes language that previously implied
  optional dependencies.
* Tool catalog authoring guidance highlights that JSON metadata in
  `tooling/catalog/` ships as part of the standalone `tooling_spec` package and
  is consumed by wrappers in `pyqa.catalog`.

## 🧭 Architecture Verification

Run the dependency graph generator before tagging a release to confirm that
intra-package imports still respect the intended layering rules:

```bash
uv run python reorg/scripts/generate_dependency_graph.py \
  --output reorg/artifacts/phase6/pyqa_dependency_graph.json
```

Review the histogram in the generated JSON to ensure no new high-fan-in modules
were introduced during the final refactor.

## 🚀 Release Sequencing

1. Bump versions for both `pyqa` and `tooling_spec` in `pyproject.toml`.
2. Regenerate lockfiles (`uv lock --refresh`) and run the full quality gate:
   `./lint -n` followed by `uv run pytest`.
3. Publish `tooling_spec` to the internal index, tag the commit, then publish
   the `pyqa` package referencing the released spec.
4. Update downstream automation (Git hooks, CI containers) to consume the new
   tags immediately—missing tree-sitter or spaCy dependencies must fail fast.

## 📈 Post-release Monitoring

* Track plugin feedback to validate that the `tooling_spec` API meets third
  party requirements; schedule schema increments when new strategy fields are
  requested.
* Monitor telemetry for CLI startup failures that indicate missing spaCy models
  or tree-sitter grammars and document fixes in the troubleshooting guide.
* Capture upgrade notes for teams migrating from pre-reorg layouts so they can
  adjust imports without forensic diffing.

Phase 6 closes the module reorganisation effort. Subsequent work should focus
on incremental improvements, schema evolution, and monitoring the health of the
new compliance/diagnostics/reporting boundaries.
