# SPDX-License-Identifier: MIT
"""Docstring quality linter backed by Tree-sitter structure and spaCy NLP."""

from __future__ import annotations

import ast
import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..analysis.spacy.loader import load_language
from ..analysis.treesitter.grammars import ensure_language
from ..analysis.treesitter.resolver import _build_parser_loader
from ..cli.commands.lint.preparation import PreparedLintState
from ..core.models import Diagnostic, ToolExitCategory, ToolOutcome
from ..core.severity import Severity
from ..filesystem.paths import normalize_path_key
from .base import InternalLintReport
from .utils import collect_python_files

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from tree_sitter import Node
else:  # pragma: no cover - runtime fallback uses ``Any`` to avoid hard dependency
    Node = Any


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

    def __init__(self, source: str, parser: Any) -> None:
        self._source = source
        self._source_bytes = source.encode("utf-8")
        self._parser = parser
        tree = self._parser.parse(self._source_bytes)
        self._records: dict[tuple[str, str | None, int], _DocstringRecord] = {}
        self._module_record = self._extract_module_record(tree.root_node)
        self._visit(tree.root_node)

    def _visit(self, node: Node) -> None:
        for child in node.children:
            if child.type == "decorated_definition":
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
        doc_node = None
        for child in root.named_children:
            if child.type == "expression_statement":
                candidate = self._string_literal_child(child)
                if candidate is not None:
                    doc_node = candidate
                break
            if child.type not in {"comment"}:
                break
        doc = self._literal_from_node(doc_node) if doc_node is not None else None
        lineno = root.start_point[0] + 1
        doc_lineno = doc_node.start_point[0] + 1 if doc_node is not None else None
        record = _DocstringRecord(kind="module", name=None, lineno=lineno, docstring=doc, doc_lineno=doc_lineno)
        self._records[("module", None, lineno)] = record
        return record

    def _register_definition(self, node: Node) -> None:
        kind = "function" if "function" in node.type else "class"
        name_node = node.child_by_field_name("name")
        name = self._slice(name_node) if name_node is not None else None
        lineno = node.start_point[0] + 1
        doc_node = self._extract_docstring_node(node)
        doc = self._literal_from_node(doc_node) if doc_node is not None else None
        doc_lineno = doc_node.start_point[0] + 1 if doc_node is not None else None
        record = _DocstringRecord(kind=kind, name=name, lineno=lineno, docstring=doc, doc_lineno=doc_lineno)
        self._records[(kind, name, lineno)] = record

    def _extract_docstring_node(self, node: Node) -> Node | None:
        body = node.child_by_field_name("body")
        if body is None:
            return None
        for child in body.named_children:
            if child.type == "expression_statement":
                string_node = self._string_literal_child(child)
                if string_node is not None:
                    return string_node
            if child.type not in {"pass_statement"}:
                break
        return None

    def _string_literal_child(self, node: Node) -> Node | None:
        for child in node.children:
            if child.type in {"string", "concatenated_string"}:
                return child
        return None

    def _slice(self, node: Node | None) -> str | None:
        if node is None:
            return None
        start, end = node.start_byte, node.end_byte
        return self._source_bytes[start:end].decode("utf-8")

    def _literal_from_node(self, node: Node | None) -> str | None:
        literal = self._slice(node)
        if literal is None:
            return None
        try:
            return ast.literal_eval(literal)
        except (SyntaxError, ValueError):
            return literal.strip("\"'")

    def get(self, kind: str, name: str | None, lineno: int) -> _DocstringRecord | None:
        return self._records.get((kind, name, lineno))

    @property
    def module_record(self) -> _DocstringRecord:
        return self._module_record


def _resolve_python_parser() -> Any:
    factory = _build_parser_loader()
    if factory is None:
        raise RuntimeError(
            "tree_sitter language bindings unavailable; install tree-sitter >=0.20",
        )
    parser = factory.create("python")
    if parser is not None:
        return parser
    language = ensure_language("python")
    if language is None:
        raise RuntimeError(
            "Unable to compile Python Tree-sitter grammar automatically.",
        )
    parser_cls = getattr(importlib.import_module("tree_sitter"), "Parser", None)
    if parser_cls is None:
        raise RuntimeError("tree_sitter.Parser not available even after grammar compilation")
    parser = parser_cls()
    parser.set_language(language)
    return parser


class DocstringLinter:
    """Perform docstring quality checks using Tree-sitter and spaCy."""

    def __init__(self) -> None:
        self._model_name = "en_core_web_sm"
        self._parser = _resolve_python_parser()
        self._nlp = load_language(self._model_name)
        self._nlp_missing = self._nlp is None
        self._warnings: set[str] = set()

    def lint_paths(self, files: Sequence[Path]) -> list[DocstringIssue]:
        issues: list[DocstringIssue] = []
        for path in files:
            issues.extend(self._lint_file(path))
        if self._nlp_missing:
            self._warnings.add(
                f"spaCy model '{self._model_name}' unavailable; docstring analysis is running without NLP enrichment.",
            )
        return issues

    def consume_warnings(self) -> list[str]:
        warnings = sorted(self._warnings)
        self._warnings.clear()
        return warnings

    def _lint_file(self, path: Path) -> list[DocstringIssue]:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            return [DocstringIssue(path=path, line=1, message=f"Failed to read file: {exc}")]

        try:
            module = ast.parse(source)
        except SyntaxError as exc:
            return [DocstringIssue(path=path, line=exc.lineno or 1, message=f"Syntax error: {exc.msg}")]

        ts_index = _TreeSitterDocstrings(source, parser=self._parser)
        issues: list[DocstringIssue] = []

        module_record = ts_index.module_record
        issues.extend(self._check_module_docstring(path, module_record))

        for node in module.body:
            issues.extend(self._lint_definition(path, node, ts_index))
        return issues

    def _lint_definition(
        self,
        path: Path,
        node: ast.stmt,
        ts_index: _TreeSitterDocstrings,
    ) -> list[DocstringIssue]:
        issues: list[DocstringIssue] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            record = ts_index.get("function", node.name, node.lineno)
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
            record = ts_index.get("class", node.name, node.lineno)
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
        issues: list[DocstringIssue] = []
        doc = record.docstring if record and record.docstring else None
        line = record.doc_lineno if record and record.doc_lineno else node.lineno
        if not doc:
            issues.append(DocstringIssue(path=path, line=line, message=f"Class '{node.name}' is missing a docstring"))
        else:
            issues.extend(self._check_summary(path, line, doc))
        return issues

    def _check_function_docstring(
        self,
        *,
        path: Path,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        record: _DocstringRecord | None,
    ) -> list[DocstringIssue]:
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

        issues.extend(self._check_summary(path, doc_line, doc))

        if params and not _has_args_section(doc):
            issues.append(
                DocstringIssue(
                    path=path,
                    line=doc_line,
                    message=f"Function '{node.name}' is missing an Args section",
                ),
            )
        if returns_value and not _has_returns_section(doc):
            issues.append(
                DocstringIssue(
                    path=path,
                    line=doc_line,
                    message=f"Function '{node.name}' is missing a Returns section",
                ),
            )
        if yields_value and not _has_yields_section(doc):
            issues.append(
                DocstringIssue(
                    path=path,
                    line=doc_line,
                    message=f"Function '{node.name}' is missing a Yields section",
                ),
            )
        return issues

    def _check_summary(self, path: Path, line: int, docstring: str) -> list[DocstringIssue]:
        issues: list[DocstringIssue] = []
        summary = _extract_summary_line(docstring)
        if not summary:
            issues.append(DocstringIssue(path=path, line=line, message="Docstring summary is empty"))
            return issues
        if len(summary) > 120:
            issues.append(
                DocstringIssue(
                    path=path,
                    line=line,
                    message="Docstring summary exceeds 120 characters",
                ),
            )
        if self._nlp is not None:
            doc = self._nlp(summary)
            first_token = next(iter(doc), None)
            if first_token is not None and first_token.pos_ not in {"VERB", "AUX"}:
                issues.append(
                    DocstringIssue(
                        path=path,
                        line=line,
                        message="Docstring summary should start with an imperative verb",
                    ),
                )
        return issues


def _parameter_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
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
    if node.returns is None:
        return False
    if isinstance(node.returns, ast.Constant) and node.returns.value is None:
        return False
    if isinstance(node.returns, ast.Name) and node.returns.id == "None":
        return False
    return True


def _function_yields_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(child, (ast.Yield, ast.YieldFrom)) for child in ast.walk(node))


def _has_args_section(docstring: str) -> bool:
    lowered = {entry.strip().lower() for entry in docstring.splitlines()}
    return any(entry.startswith("args:") or entry.startswith("arguments:") for entry in lowered)


def _has_returns_section(docstring: str) -> bool:
    lowered = {entry.strip().lower() for entry in docstring.splitlines()}
    return any(entry.startswith(prefix) for entry in lowered for prefix in ("returns:", "return:"))


def _has_yields_section(docstring: str) -> bool:
    lowered = {entry.strip().lower() for entry in docstring.splitlines()}
    return any(entry.startswith("yields:") or entry.startswith("yield:") for entry in lowered)


def _extract_summary_line(docstring: str) -> str:
    stripped = docstring.strip()
    if not stripped:
        return ""
    for line in stripped.splitlines():
        clean = line.strip()
        if clean:
            return clean
    return ""


def _collect_python_files(state: PreparedLintState) -> list[Path]:
    options = state.options.target_options
    candidates: set[Path] = set()
    root = options.root.resolve()
    paths = [path.resolve() for path in options.paths]
    if not paths and not options.dirs:
        paths.append(root)
    for path in paths:
        if _is_excluded(path, options.exclude, root):
            continue
        if path.is_file() and path.suffix in {".py", ".pyi"}:
            candidates.add(path)
        elif path.is_dir():
            candidates.update(_walk_python_files(path, options.exclude, root))
    for directory in options.dirs:
        dir_path = directory.resolve()
        candidates.update(_walk_python_files(dir_path, options.exclude, root))
    return sorted(candidates)


def _walk_python_files(directory: Path, exclude: Iterable[Path], root: Path) -> set[Path]:
    excluded = [path.resolve() for path in exclude]
    results: set[Path] = set()
    for candidate in directory.rglob("*.py"):
        if _is_excluded(candidate, excluded, root):
            continue
        results.add(candidate)
    for candidate in directory.rglob("*.pyi"):
        if _is_excluded(candidate, excluded, root):
            continue
        results.add(candidate)
    return results


def _is_excluded(path: Path, excluded: Iterable[Path], root: Path) -> bool:
    path = path.resolve()
    for skip in excluded:
        try:
            path.relative_to(skip)
        except ValueError:
            continue
        return True
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    if any(part in ALWAYS_EXCLUDE_DIRS for part in relative.parts):
        return True
    return False


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


def _derive_issue_code(message: str) -> str:
    """Return a stable diagnostic code derived from a docstring message.

    Args:
        message: Human-readable docstring violation message.

    Returns:
        str: Namespaced diagnostic code used for reporting and suppression.
    """

    lowered = message.lower()
    if "missing module docstring" in lowered:
        return "docstrings:missing-module-docstring"
    if "missing a docstring" in lowered:
        if "class" in lowered:
            return "docstrings:missing-class-docstring"
        if "function" in lowered:
            return "docstrings:missing-function-docstring"
        return "docstrings:missing-docstring"
    if "missing an args section" in lowered:
        return "docstrings:missing-args-section"
    if "missing a returns section" in lowered:
        return "docstrings:missing-returns-section"
    if "missing a yields section" in lowered:
        return "docstrings:missing-yields-section"
    if "summary is empty" in lowered:
        return "docstrings:empty-summary"
    if "summary exceeds" in lowered:
        return "docstrings:long-summary"
    if "summary should start" in lowered:
        return "docstrings:summary-not-imperative"
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
    files = collect_python_files(state)
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    diagnostics: list[Diagnostic] = []
    exit_category = ToolExitCategory.SUCCESS
    returncode = 0
    files_tuple = tuple(files)

    if not files:
        message = "No Python files discovered for docstring analysis"
        stdout_lines.append(message)
        outcome = ToolOutcome(
            tool="docstrings",
            action="check",
            returncode=0,
            stdout=stdout_lines,
            stderr=stderr_lines,
            diagnostics=diagnostics,
            exit_category=exit_category,
        )
        return InternalLintReport(outcome=outcome, files=files_tuple)

    try:
        linter = DocstringLinter()
    except RuntimeError as exc:
        warning = str(exc)
        stderr_lines.append(warning)
        outcome = ToolOutcome(
            tool="docstrings",
            action="check",
            returncode=2,
            stdout=stdout_lines,
            stderr=stderr_lines,
            diagnostics=diagnostics,
            exit_category=ToolExitCategory.TOOL_FAILURE,
        )
        return InternalLintReport(outcome=outcome, files=files_tuple)

    issues = linter.lint_paths(files)
    for warning in linter.consume_warnings():
        stderr_lines.append(warning)

    if issues:
        exit_category = ToolExitCategory.DIAGNOSTIC
        returncode = 1
        for issue in issues:
            normalized = normalize_path_key(issue.path, base_dir=state.root)
            message = f"{normalized}:{issue.line}: {issue.message}"
            stdout_lines.append(message)
            diagnostics.append(_issue_to_diagnostic(issue, root=state.root))
        summary = f"Docstring linter reported {len(issues)} issue(s) across {len(files)} file(s)"
        stdout_lines.append(summary)
    else:
        message = f"Docstring checks passed for {len(files)} file(s)"
        stdout_lines.append(message)

    outcome = ToolOutcome(
        tool="docstrings",
        action="check",
        returncode=returncode,
        stdout=stdout_lines,
        stderr=stderr_lines,
        diagnostics=diagnostics,
        exit_category=exit_category,
    )
    return InternalLintReport(outcome=outcome, files=files_tuple)


__all__ = [
    "DocstringIssue",
    "DocstringLinter",
    "run_docstring_linter",
]
