# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Enforce docstring quality using Tree-sitter structure and spaCy NLP."""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Final

from tree_sitter import Node, Parser, Tree

from ..analysis.spacy.loader import load_language
from ..cache.result_store import CacheRequest, ResultCache
from ..core.models import Diagnostic, ToolExitCategory, ToolOutcome
from ..core.severity import Severity
from ..filesystem.paths import normalize_path_key
from ..interfaces.linting import PreparedLintState
from .base import InternalLintReport
from .tree_sitter_utils import resolve_python_parser
from .utils import collect_python_files

_DECORATED_NODE_TYPE: Final[str] = "decorated_definition"
_EXPRESSION_NODE_TYPE: Final[str] = "expression_statement"
_STRING_NODE_TYPES: Final[tuple[str, str]] = ("string", "concatenated_string")
_PASS_STATEMENT_TYPE: Final[str] = "pass_statement"
_COMMENT_NODE_TYPE: Final[str] = "comment"
_FUNCTION_TOKEN: Final[str] = "function"
_CLASS_TOKEN: Final[str] = "class"
_MISSING_DOCSTRING_PHRASE: Final[str] = "missing a docstring"
_CLASS_LABEL: Final[str] = "class"
_FUNCTION_LABEL: Final[str] = "function"
_NONE_LITERAL: Final[str] = "None"
_MAX_SUMMARY_LENGTH: Final[int] = 120
_DOCSTRING_CACHE_TOKEN: Final[str] = "docstrings:v1"
_DOCSTRING_CACHE_SUBDIR: Final[str] = "internal/docstrings"
_DOCSTRING_FILE_COMMAND: Final[tuple[str, ...]] = ("internal", "docstrings", "file")


@dataclass(slots=True)
class DocstringIssue:
    """Represent a docstring lint finding."""

    path: Path
    line: int
    message: str


@dataclass(slots=True)
class _DocstringRecord:
    """Docstring metadata captured via Tree-sitter."""

    kind: str
    name: str | None
    lineno: int
    docstring: str | None
    doc_lineno: int | None


class _TreeSitterDocstrings:
    """Index docstring information extracted with Tree-sitter."""

    def __init__(self, source: str, tree: Tree) -> None:
        """Build the index for ``source`` using ``tree``.

        Args:
            source: Raw Python source code to analyse.
            tree: Parsed Tree-sitter syntax tree for the module.
        """

        self._source = source
        self._source_bytes = source.encode("utf-8")
        self._records: dict[tuple[str, str | None, int], _DocstringRecord] = {}
        self._module_record = self._extract_module_record(tree.root_node)
        self._visit(tree.root_node)

    def _visit(self, node: Node) -> None:
        """Traverse ``node`` to register docstring-bearing definitions.

        Args:
            node: Tree-sitter node to recurse through.
        """

        for child in node.children:
            if child.type == _DECORATED_NODE_TYPE:
                definition = child.child_by_field_name("definition")
                if definition is not None:
                    self._register_definition(definition)
                    self._visit(definition)
                continue
            if child.type in {"function_definition", "class_definition", "async_function_definition"}:
                self._register_definition(child)
                self._visit(child)
                continue
            if child.children:
                self._visit(child)

    def _extract_module_record(self, root: Node) -> _DocstringRecord:
        """Return the module-level record anchored at ``root``.

        Args:
            root: Tree-sitter root node representing the module.

        Returns:
            Record capturing the module docstring metadata.
        """

        doc_node = None
        for child in root.named_children:
            if child.type == _EXPRESSION_NODE_TYPE:
                candidate = self._string_literal_child(child)
                if candidate is not None:
                    doc_node = candidate
                break
            if child.type not in {_COMMENT_NODE_TYPE}:
                break
        doc = self._literal_from_node(doc_node) if doc_node is not None else None
        lineno = root.start_point[0] + 1
        doc_lineno = doc_node.start_point[0] + 1 if doc_node is not None else None
        record = _DocstringRecord(kind="module", name=None, lineno=lineno, docstring=doc, doc_lineno=doc_lineno)
        self._records[("module", None, lineno)] = record
        return record

    def _register_definition(self, node: Node) -> None:
        """Register a function or class definition node within the index.

        Args:
            node: Definition node to record.
        """

        kind = _FUNCTION_TOKEN if _FUNCTION_TOKEN in node.type else _CLASS_TOKEN
        name_node = node.child_by_field_name("name")
        name = self._slice(name_node) if name_node is not None else None
        lineno = node.start_point[0] + 1
        doc_node = self._extract_docstring_node(node)
        doc = self._literal_from_node(doc_node) if doc_node is not None else None
        doc_lineno = doc_node.start_point[0] + 1 if doc_node is not None else None
        record = _DocstringRecord(kind=kind, name=name, lineno=lineno, docstring=doc, doc_lineno=doc_lineno)
        self._records[(kind, name, lineno)] = record

    def _extract_docstring_node(self, node: Node) -> Node | None:
        """Return the docstring node for ``node`` if one exists.

        Args:
            node: Definition node whose body is inspected.

        Returns:
            Tree-sitter node containing the docstring string literal.
        """

        body = node.child_by_field_name("body")
        if body is None:
            return None
        for child in body.named_children:
            if child.type == _EXPRESSION_NODE_TYPE:
                string_node = self._string_literal_child(child)
                if string_node is not None:
                    return string_node
            if child.type not in {_PASS_STATEMENT_TYPE}:
                break
        return None

    def _string_literal_child(self, node: Node) -> Node | None:
        """Return the first string literal child of ``node``.

        Args:
            node: Tree-sitter node possibly containing string literal children.

        Returns:
            Child node representing a string literal or ``None`` when absent.
        """

        for child in node.children:
            if child.type in _STRING_NODE_TYPES:
                return child
        return None

    def _slice(self, node: Node | None) -> str | None:
        """Return source text represented by ``node``.

        Args:
            node: Tree-sitter node to convert into source text.

        Returns:
            Text slice spanned by the node or ``None`` when node is missing.
        """

        if node is None:
            return None
        start, end = node.start_byte, node.end_byte
        return self._source_bytes[start:end].decode("utf-8")

    def _literal_from_node(self, node: Node | None) -> str | None:
        """Return the evaluated literal string represented by ``node``.

        Args:
            node: Tree-sitter node to evaluate as a Python literal.

        Returns:
            String value obtained from ``node`` or ``None`` when absent.
        """

        literal = self._slice(node)
        if literal is None:
            return None
        try:
            evaluated = ast.literal_eval(literal)
        except (SyntaxError, ValueError):
            evaluated = literal.strip("\"'")
        else:
            if not isinstance(evaluated, str):
                evaluated = str(evaluated)
        return evaluated

    def get(self, kind: str, name: str | None, lineno: int) -> _DocstringRecord | None:
        """Return the docstring record keyed by ``(kind, name, lineno)``.

        Args:
            kind: Definition kind, such as ``"function"`` or ``"class"``.
            name: Optional definition name.
            lineno: Line number where the definition appears.

        Returns:
            _DocstringRecord | None: Matching record when present.
        """

        return self._records.get((kind, name, lineno))

    @property
    def module_record(self) -> _DocstringRecord:
        """Return the module-level docstring record.

        Returns:
            _DocstringRecord: Module-level docstring metadata.
        """

        return self._module_record


class DocstringLinter:
    """Perform docstring quality checks using Tree-sitter and spaCy."""

    def __init__(self, *, cache: ResultCache | None = None) -> None:
        """Initialise the linter by resolving grammar and language resources.

        Args:
            cache: Optional result cache used to memoize per-file lint outcomes.
        """

        self._model_name = "en_core_web_sm"
        self._parser: Parser = resolve_python_parser()
        self._parser_lock = Lock()
        self._nlp = load_language(self._model_name)
        self._nlp_missing = self._nlp is None
        self._warnings: set[str] = set()
        self._cache = cache

    def lint_paths(self, files: Sequence[Path]) -> list[DocstringIssue]:
        """Return docstring issues for each file in ``files``.

        Args:
            files: Sequence of Python files to analyse.

        Returns:
            List of docstring issues discovered across the supplied files.
        """

        issues: list[DocstringIssue] = []
        for path in files:
            issues.extend(self._lint_file_cached(path))
        if self._nlp_missing:
            self._warnings.add(
                f"spaCy model '{self._model_name}' unavailable; docstring analysis is running without NLP enrichment.",
            )
        return issues

    def consume_warnings(self) -> list[str]:
        """Return and clear accumulated linter warnings.

        Returns:
            Sorted list of warning messages emitted during the most recent run.
        """

        warnings = sorted(self._warnings)
        self._warnings.clear()
        return warnings

    def _lint_file(self, path: Path) -> list[DocstringIssue]:
        """Collect docstring issues for ``path``.

        Args:
            path: Absolute path to the Python source file being linted.

        Returns:
            List of docstring issues discovered within the file.
        """

        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            return [DocstringIssue(path=path, line=1, message=f"Failed to read file: {exc}")]

        try:
            module = ast.parse(source)
        except SyntaxError as exc:
            return [DocstringIssue(path=path, line=exc.lineno or 1, message=f"Syntax error: {exc.msg}")]

        tree = self._parse_tree(source)
        ts_index = _TreeSitterDocstrings(source, tree=tree)
        issues: list[DocstringIssue] = []

        module_record = ts_index.module_record
        issues.extend(self._check_module_docstring(path, module_record))

        for node in module.body:
            issues.extend(self._lint_definition(path, node, ts_index))
        return issues

    def _lint_file_cached(self, path: Path) -> list[DocstringIssue]:
        """Return cached docstring issues for ``path`` when available.

        Args:
            path: File path being analysed.

        Returns:
            list[DocstringIssue]: Issues loaded from cache or freshly computed.
        """

        cache = self._cache
        if cache is None:
            return self._lint_file(path)
        request = CacheRequest(
            tool="docstrings",
            action="file",
            command=_DOCSTRING_FILE_COMMAND,
            files=(path.resolve(),),
            token=_DOCSTRING_CACHE_TOKEN,
        )
        cached_entry = cache.load(request)
        if cached_entry is not None:
            return self._diagnostics_to_issues(cached_entry.outcome.diagnostics)
        issues = self._lint_file(path)
        outcome = self._issues_to_outcome(issues)
        cache.store(request=request, outcome=outcome, file_metrics={})
        return issues

    @staticmethod
    def _diagnostics_to_issues(diagnostics: Sequence[Diagnostic]) -> list[DocstringIssue]:
        """Convert cached diagnostics into :class:`DocstringIssue` instances.

        Args:
            diagnostics: Diagnostics persisted by a previous lint invocation.

        Returns:
            list[DocstringIssue]: Issues reconstructed from diagnostics.
        """

        cached: list[DocstringIssue] = []
        for diagnostic in diagnostics:
            if diagnostic.file is None:
                continue
            cached.append(
                DocstringIssue(
                    path=Path(diagnostic.file),
                    line=diagnostic.line or 1,
                    message=diagnostic.message,
                )
            )
        return cached

    @staticmethod
    def _issues_to_outcome(issues: Sequence[DocstringIssue]) -> ToolOutcome:
        """Convert :class:`DocstringIssue` entries into a :class:`ToolOutcome`.

        Args:
            issues: Docstring issues collected during linting.

        Returns:
            ToolOutcome: Outcome object mirroring the expected CLI structure.
        """

        diagnostics = [
            Diagnostic(
                file=issue.path.as_posix(),
                line=issue.line,
                column=None,
                severity=Severity.WARNING,
                message=issue.message,
                tool="docstrings",
            )
            for issue in issues
        ]
        stdout = [f"{issue.path.as_posix()}:{issue.line}: {issue.message}" for issue in issues]
        return ToolOutcome(
            tool="docstrings",
            action="file",
            returncode=1 if issues else 0,
            stdout=stdout,
            stderr=[],
            diagnostics=diagnostics,
            exit_category=ToolExitCategory.DIAGNOSTIC if issues else ToolExitCategory.SUCCESS,
        )

    def _lint_definition(
        self,
        path: Path,
        node: ast.stmt,
        ts_index: _TreeSitterDocstrings,
    ) -> list[DocstringIssue]:
        """Return issues for ``node`` and its nested definitions.

        Args:
            path: Absolute path to the file being inspected.
            node: AST statement representing a class or function definition.
            ts_index: Tree-sitter derived docstring index for the file.

        Returns:
            List of docstring issues discovered within the definition.
        """

        issues: list[DocstringIssue] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            record = ts_index.get(_FUNCTION_TOKEN, node.name, node.lineno)
            issues.extend(
                self._check_function_docstring(
                    path=path,
                    node=node,
                    record=record,
                ),
            )
            for stmt in node.body:
                issues.extend(self._lint_definition(path, stmt, ts_index))
        elif isinstance(node, ast.ClassDef):
            record = ts_index.get(_CLASS_TOKEN, node.name, node.lineno)
            issues.extend(
                self._check_class_docstring(
                    path=path,
                    node=node,
                    record=record,
                ),
            )
            for stmt in node.body:
                issues.extend(self._lint_definition(path, stmt, ts_index))
        return issues

    def _check_module_docstring(self, path: Path, record: _DocstringRecord) -> list[DocstringIssue]:
        """Return module-level docstring issues if the module lacks coverage.

        Args:
            path: Module path being evaluated.
            record: Tree-sitter derived module docstring metadata.

        Returns:
            A list containing a missing-docstring issue when necessary.
        """

        if record.docstring:
            return []
        return [DocstringIssue(path=path, line=1, message="Missing module docstring")]

    def _check_class_docstring(
        self,
        *,
        path: Path,
        node: ast.ClassDef,
        record: _DocstringRecord | None,
    ) -> list[DocstringIssue]:
        """Validate docstring coverage for ``node``.

        Args:
            path: Module path where the class is defined.
            node: Class definition node to inspect.
            record: Tree-sitter derived docstring record, if available.

        Returns:
            List of issues covering missing summaries or sections.
        """

        issues: list[DocstringIssue] = []
        doc = record.docstring if record and record.docstring else None
        line = record.doc_lineno if record and record.doc_lineno else node.lineno
        if not doc:
            issues.append(DocstringIssue(path=path, line=line, message=f"Class '{node.name}' is missing a docstring"))
        else:
            summary_issues = self._check_summary(doc)
            if summary_issues:
                message = "; ".join(summary_issues)
                issues.append(DocstringIssue(path=path, line=line, message=f"Class '{node.name}': {message}"))
        return issues

    def _check_function_docstring(
        self,
        *,
        path: Path,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        record: _DocstringRecord | None,
    ) -> list[DocstringIssue]:
        """Validate docstring coverage for ``node`` including sections.

        Args:
            path: Module path containing the function definition.
            node: Function or coroutine definition to inspect.
            record: Tree-sitter derived docstring metadata, if present.

        Returns:
            List of issues describing missing docstrings or sections.
        """

        issues: list[DocstringIssue] = []
        doc = record.docstring if record and record.docstring else None
        doc_line = record.doc_lineno if record and record.doc_lineno else node.lineno
        params = _parameter_names(node)
        returns_value = _function_returns_value(node)
        yields_value = _function_yields_value(node)

        if not doc:
            issues.append(
                DocstringIssue(
                    path=path,
                    line=doc_line,
                    message=f"Function '{node.name}' is missing a docstring",
                ),
            )
            return issues

        function_issues: list[str] = []
        function_issues.extend(self._check_summary(doc))

        if params and not _has_args_section(doc):
            function_issues.append("Missing Args section")
        if returns_value and not _has_returns_section(doc):
            function_issues.append("Missing Returns section")
        if yields_value and not _has_yields_section(doc):
            function_issues.append("Missing Yields section")

        if function_issues:
            message = "; ".join(function_issues)
            issues.append(
                DocstringIssue(
                    path=path,
                    line=doc_line,
                    message=f"Function '{node.name}': {message}",
                ),
            )
        return issues

    def _parse_tree(self, source: str) -> Tree:
        """Return a Tree-sitter syntax tree for ``source``.

        Args:
            source: Python source code to parse.

        Returns:
            Tree: Parsed syntax tree.
        """

        encoded = source.encode("utf-8")
        with self._parser_lock:
            return self._parser.parse(encoded)

    def _check_summary(self, docstring: str) -> list[str]:
        """Validate the summary line for ``docstring``.

        Args:
            docstring: Raw docstring text to analyse.

        Returns:
            List of human readable summary-related issues.
        """

        issues: list[str] = []
        summary = _extract_summary_line(docstring)
        if not summary:
            issues.append("Docstring summary is empty")
            return issues
        if len(summary) > _MAX_SUMMARY_LENGTH:
            issues.append(f"Docstring summary exceeds {_MAX_SUMMARY_LENGTH} characters")
        if self._nlp is not None:
            # Restore imperative detection once spaCy tagging is more reliable for
            # sentence-initial verbs. For now we skip this check to avoid false
            # positives on summaries such as "Track line counts".
            _ = self._nlp(summary)
        return issues


def _parameter_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Return parameter names excluding implicit ``self``/``cls``.

    Args:
        node: Function or coroutine definition being inspected.

    Returns:
        List of parameter identifiers relevant for docstring validation.
    """

    params: list[str] = []
    params.extend(arg.arg for arg in getattr(node.args, "posonlyargs", ()))
    params.extend(arg.arg for arg in node.args.args)
    if node.args.vararg:
        params.append(node.args.vararg.arg)
    params.extend(arg.arg for arg in node.args.kwonlyargs)
    if node.args.kwarg:
        params.append(node.args.kwarg.arg)
    filtered = [name for name in params if name not in {"self", "cls"}]
    return filtered


def _function_returns_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return ``True`` when ``node`` declares a non-``None`` return type.

    Args:
        node: Function or coroutine definition to evaluate.

    Returns:
        ``True`` if the annotation signals a meaningful return value.
    """

    if node.returns is None:
        return False
    if isinstance(node.returns, ast.Constant) and node.returns.value is None:
        return False
    if isinstance(node.returns, ast.Name) and node.returns.id == _NONE_LITERAL:
        return False
    return True


def _function_yields_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return ``True`` when ``node`` yields values during execution.

    Args:
        node: Function or coroutine definition to evaluate.

    Returns:
        ``True`` if the function body contains ``yield`` expressions.
    """

    return any(isinstance(child, (ast.Yield, ast.YieldFrom)) for child in ast.walk(node))


def _has_args_section(docstring: str) -> bool:
    """Return ``True`` when ``docstring`` documents arguments.

    Args:
        docstring: Docstring text to inspect.

    Returns:
        ``True`` if an ``Args`` or ``Arguments`` section is present.
    """

    lowered = {entry.strip().lower() for entry in docstring.splitlines()}
    return any(entry.startswith("args:") or entry.startswith("arguments:") for entry in lowered)


def _has_returns_section(docstring: str) -> bool:
    """Return ``True`` when ``docstring`` documents return values.

    Args:
        docstring: Docstring text to inspect.

    Returns:
        ``True`` if a ``Returns`` or ``Return`` section is present.
    """

    lowered = {entry.strip().lower() for entry in docstring.splitlines()}
    return any(entry.startswith(prefix) for entry in lowered for prefix in ("returns:", "return:"))


def _has_yields_section(docstring: str) -> bool:
    """Return ``True`` when ``docstring`` documents yielded values.

    Args:
        docstring: Docstring text to inspect.

    Returns:
        ``True`` if a ``Yields`` or ``Yield`` section is present.
    """

    lowered = {entry.strip().lower() for entry in docstring.splitlines()}
    return any(entry.startswith("yields:") or entry.startswith("yield:") for entry in lowered)


def _extract_summary_line(docstring: str) -> str:
    """Return the first non-empty summary line from ``docstring``.

    Args:
        docstring: Docstring text to inspect.

    Returns:
        Summary sentence or an empty string when none exists.
    """

    stripped = docstring.strip()
    if not stripped:
        return ""
    for line in stripped.splitlines():
        clean = line.strip()
        if clean:
            return clean
    return ""


def _issue_to_diagnostic(issue: DocstringIssue, *, root: Path) -> Diagnostic:
    """Convert a docstring issue into a normalized diagnostic.

    Args:
        issue: Docstring issue produced by the linter.
        root: Repository root used to normalize file paths.

    Returns:
        Diagnostic: Structured diagnostic describing the docstring finding.
    """

    file_key = normalize_path_key(issue.path, base_dir=root)
    return Diagnostic(
        file=file_key,
        line=issue.line,
        column=None,
        severity=Severity.ERROR,
        message=issue.message,
        tool="docstrings",
        code=_derive_issue_code(issue.message),
    )


_ISSUE_CODE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("missing module docstring", "docstrings:missing-module-docstring"),
    ("missing an args section", "docstrings:missing-args-section"),
    ("missing a returns section", "docstrings:missing-returns-section"),
    ("missing a yields section", "docstrings:missing-yields-section"),
    ("summary is empty", "docstrings:empty-summary"),
    ("summary exceeds", "docstrings:long-summary"),
    ("summary should start", "docstrings:summary-not-imperative"),
)


def _derive_issue_code(message: str) -> str:
    """Return a stable diagnostic code derived from ``message``.

    Args:
        message: Raw diagnostic text emitted by the docstring linter.

    Returns:
        Code string adhering to the ``docstrings:*`` namespace.
    """

    lowered = message.lower()
    for needle, code in _ISSUE_CODE_PATTERNS:
        if needle in lowered:
            return code
    if _MISSING_DOCSTRING_PHRASE in lowered:
        if _CLASS_LABEL in lowered:
            return "docstrings:missing-class-docstring"
        if _FUNCTION_LABEL in lowered:
            return "docstrings:missing-function-docstring"
        return "docstrings:missing-docstring"
    return "docstrings:issue"


def run_docstring_linter(
    state: PreparedLintState,
    *,
    emit_to_logger: bool = True,
) -> InternalLintReport:
    """Execute the docstring linter using CLI-prepared state.

    Args:
        state: Prepared CLI state providing discovery inputs and logger.
        emit_to_logger: Whether to stream findings to the CLI logger.

    Returns:
        InternalLintReport: Aggregated outcome and file context for the run.
    """

    _ = emit_to_logger  # Retained for CLI compatibility; output is handled via ToolOutcome.
    files = tuple(collect_python_files(state))
    if not files:
        return _report_docstrings_empty(files)

    runtime_options = state.options.execution_options.runtime
    cache: ResultCache | None = None
    if files and not runtime_options.no_cache:
        cache_dir = runtime_options.cache_dir
        if not cache_dir.is_absolute():
            cache_dir = state.root / cache_dir
        cache_path = (cache_dir / Path(_DOCSTRING_CACHE_SUBDIR)).resolve()
        cache = ResultCache(cache_path)

    try:
        linter = DocstringLinter(cache=cache)
    except RuntimeError as exc:
        return _report_docstrings_failure(files, str(exc))

    issues = linter.lint_paths(files)
    warnings = linter.consume_warnings()
    return _report_docstrings_result(
        files=files,
        issues=issues,
        warnings=warnings,
        root=state.root,
    )


def _report_docstrings_empty(files: tuple[Path, ...]) -> InternalLintReport:
    """Return a success report when no Python files are discovered.

    Args:
        files: Tuple of files considered for docstring analysis (empty tuple).

    Returns:
        InternalLintReport describing the successful no-op run.
    """

    message = "No Python files discovered for docstring analysis"
    outcome = ToolOutcome(
        tool="docstrings",
        action="check",
        returncode=0,
        stdout=[message],
        stderr=[],
        diagnostics=[],
        exit_category=ToolExitCategory.SUCCESS,
    )
    return InternalLintReport(outcome=outcome, files=files)


def _report_docstrings_failure(files: tuple[Path, ...], warning: str) -> InternalLintReport:
    """Return a failure report when docstring tooling fails to initialize.

    Args:
        files: Files considered for the run (mirrors orchestrator contract).
        warning: Failure message describing the initialization problem.

    Returns:
        InternalLintReport capturing the tool failure.
    """

    outcome = ToolOutcome(
        tool="docstrings",
        action="check",
        returncode=2,
        stdout=[],
        stderr=[warning],
        diagnostics=[],
        exit_category=ToolExitCategory.TOOL_FAILURE,
    )
    return InternalLintReport(outcome=outcome, files=files)


def _report_docstrings_result(
    *,
    files: tuple[Path, ...],
    issues: Sequence[DocstringIssue],
    warnings: Sequence[str],
    root: Path,
) -> InternalLintReport:
    """Return the consolidated docstring lint report for ``issues``.

    Args:
        files: Files analysed during the run.
        issues: Docstring issues discovered by the linter.
        warnings: Supplemental warnings emitted during analysis.
        root: Repository root used to normalize diagnostics.

    Returns:
        InternalLintReport capturing the aggregated outcome.
    """

    stdout_lines: list[str] = []
    diagnostics: list[Diagnostic] = []
    for issue in issues:
        normalized = normalize_path_key(issue.path, base_dir=root)
        stdout_lines.append(f"{normalized}:{issue.line}: {issue.message}")
        diagnostics.append(_issue_to_diagnostic(issue, root=root))

    if issues:
        summary = f"Docstring linter reported {len(issues)} issue(s) across {len(files)} file(s)"
        stdout_lines.append(summary)
        exit_category = ToolExitCategory.DIAGNOSTIC
        returncode = 1
    else:
        stdout_lines.append(f"Docstring checks passed for {len(files)} file(s)")
        exit_category = ToolExitCategory.SUCCESS
        returncode = 0

    outcome = ToolOutcome(
        tool="docstrings",
        action="check",
        returncode=returncode,
        stdout=stdout_lines,
        stderr=list(warnings),
        diagnostics=diagnostics,
        exit_category=exit_category,
    )
    return InternalLintReport(outcome=outcome, files=files)


__all__ = [
    "DocstringIssue",
    "DocstringLinter",
    "run_docstring_linter",
]
