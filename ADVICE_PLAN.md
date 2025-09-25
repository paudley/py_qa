# Advice & Highlighting Refactor Plan

## 1. Audit current pipeline
- Trace diagnostic flow from extraction to display
  * Tool raw output → `diagnostics.normalize_diagnostics`
  * Tree-sitter context (functions/classes) before formatting
  * `_render_concise`, `_render_pretty`, `_render_advice`
- Identify existing metadata: file, line, column, severity, code, message, function (Tree-sitter), tool
- Locate current string rewriting/highlighting helpers: `_highlight_for_output`, `_apply_highlighting_text`, etc.
  * Note where regex-based detection can be replaced

## 2. Annotation layer design
- Introduce `DiagnosticAnnotation` data structure capturing:
  * File path (normalized)
  * Function, class (optional)
  * Symbol list with type tags (`argument`, `variable`, `attribute`, `class`, `function`)
- Populate annotations during/after normalization
- Inputs:
  * Tree-sitter context resolver for structural info
  * spaCy for message parsing
- Implement caching (`AnnotationCache`) keyed by (tool, code, message text) to avoid repeated NLP work

## 3. spaCy integration
- Select model (e.g., `en_core_web_sm`); ensure dependency added
- Create `src/pyqa/nlp.py` helper module:
  * Load spaCy pipeline lazily; expose `analyze_message(message: str) -> ParsedResult`
  * Extract entities/noun chunks, map to symbol categories
  * Handle patterns like "function argument foo, bar" to enumerate names
- Provide fallback path if model missing (warn once, use regex heuristics)

## 4. Refactor highlighting & formatting
- Replace regex-heavy `_highlight_for_output` with formatter that consumes `DiagnosticAnnotation`
- Build styling map (file cyan, function amber, class green, arguments magenta, variables mint, attributes orange)
- For ANSI:
  * Use `rich.text.Text` segments in advice/pretty outputs
- For plain CLI:
  * Use `colorize` per token when tty enabled
- Ensure advice panel composes `Text` objects so path/function tinting survives inside panel
- Update concise/pretty rendering to leverage new annotations instead of manual replacements

## 5. SOLID advice improvements
- Use annotations to enrich heuristics:
  * Complexity: no duplicate lines, top 5 functions ranked by estimated size/complexity
  * Type annotation & magic-number advice reference specific arguments/variables
  * Packaging/encapsulation highlight classes/modules via annotations
  * Provide aggregated summaries (with counts) when multiple files involved
- Factor advice logic into `src/pyqa/reporting/advice.py`; formatting layer renders result

## 6. Testing strategy
- Unit tests for annotation caching (same message → single spaCy run)
- Tests for annotation extraction (Tree-sitter + spaCy) on representative messages
- Update snapshot tests for concise/pretty/advice (color disabled) to verify strings
- Add targeted tests ensuring highlighting (ANSI) includes escapes (e.g., regex on `colorize` output)
- Integration test running sample lint session verifying top-5 refactor summary and new highlights

## 7. Rollout & documentation
- Document spaCy dependency & model download in README and CLI help
- Provide flag to disable spaCy-based highlighting (e.g., `--no-nlp-highlights`)
- Update docs to describe new advice quality & color palette
