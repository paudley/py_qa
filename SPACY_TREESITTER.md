# SpaCy & Tree-sitter Integration Roadmap

## Objectives

- Leverage Tree-sitter for structural understanding across catalog-defined tools.
- Employ spaCy for higher-level language insights (documentation quality, guidance).
- Keep the catalog as the configuration authority by expressing new capabilities via strategies and metadata.

## Workstreams

### 1. Tree-sitter Parser Strategy

- Add `parser_treesitter` strategy entry with configuration keys (`language`, `queries`, `captures`).
- Extend the loader schema to validate Tree-sitter metadata and ensure runtimes include language grammars.
- Pilot integrations:
  - Lua (`luacheck`, `lualint`) for precise global detection.
  - Dockerfile (`dockerfilelint`) to replace regex parsing with structured spans.
- Provide tests that assert Tree-sitter snapshots are stable given catalog definitions.

### 2. Tree-sitter Fixer Pipeline

- Define `fixer` block in tool JSON allowing Tree-sitter query → replacement templates.
- Introduce an orchestrator phase that applies catalog-described patches before external tool execution.
- Deliver a prototype fixer (e.g., normalize Dockerfile ENV ordering) and measure diff output handling.

### 3. spaCy-based Diagnostic Enhancements

- Publish `analysis_spacy` strategy that consumes diagnostics + source excerpts.
- Use spaCy models to enrich advice (e.g., summarizing complex diffs, flagging ambiguous TODO comments).
- Wire into catalog via `postProcessors` lists so tools opt-in declaratively.

### 4. Docstring and Comment Auditing

- Add catalog flag (`documentationChecks`) for Python tools requiring Google-style docstrings.
- Reuse spaCy pipelines to verify docstring sections and produce normalized suggestions.
- Update tests to cover CLI advice emitted when docstrings are missing or malformed.

### 5. Contextual Suppression Suggestions

- Combine Tree-sitter spans with spaCy entity detection to recommend precise suppression locations.
- Expose helper (`catalog_suppression_suggestions`) returning line ranges and justification text.
- Teach `pyqa doctor` to surface these hints when repeated suppressions are detected.

## Enablement Tasks

- Expand `tool_definition.schema.json` with new keys (`documentation`, `fixers`, `postProcessors`).
- Ensure installer strategies can fetch Tree-sitter grammars and spaCy models on demand.
- Benchmark performance impacts; cache parsed ASTs/Doc objects keyed by file snapshot + tool.

## Success Criteria

- All new capabilities are catalog-configured—adding a tool requires zero Python edits.
- Test suite exercises Tree-sitter parsing and spaCy analysis in isolation and via orchestrator flows.
- CLI commands (`lint`, `doctor`, `tool-info`) surface richer guidance derived from the new strategies without regressions.
