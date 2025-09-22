"""Context extraction using Tree-sitter grammars."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

try:  # pragma: no cover - optional dependency gating
    from tree_sitter import Node, Parser
    from tree_sitter_languages import get_language
except ModuleNotFoundError:  # pragma: no cover - graceful degradation
    Parser = None  # type: ignore[assignment]
    Node = object  # type: ignore[misc]
    get_language = None

from .models import Diagnostic


@dataclass(slots=True)
class _ParseResult:
    tree: object
    source: bytes


class TreeSitterContextResolver:
    """Enrich diagnostics with structural context using Tree-sitter."""

    _LANGUAGE_ALIASES = {
        "python": {".py", ".pyi"},
        "markdown": {".md", ".markdown"},
        "json": {".json"},
    }

    _SUPPORTED_LANGUAGES = frozenset(_LANGUAGE_ALIASES.keys())

    def __init__(self) -> None:
        self._parsers: dict[str, Parser | None] = {}
        self._disabled: set[str] = set()

    def annotate(self, diagnostics: Iterable[Diagnostic], *, root: Path) -> None:
        root = root.resolve()
        for diag in diagnostics:
            if diag.function:
                continue
            if diag.line is None or not diag.file:
                continue
            language = self._detect_language(diag.file)
            if language is None:
                continue
            location = self._resolve_path(diag.file, root)
            if location is None or not location.is_file():
                continue
            context = self._find_context(language, location, diag.line)
            if context:
                diag.function = context

    def _detect_language(self, file_str: str) -> str | None:
        path = Path(file_str)
        suffix = path.suffix.lower()
        for language, suffixes in self._LANGUAGE_ALIASES.items():
            if suffix in suffixes:
                return language
        return None

    def _resolve_path(self, file_str: str, root: Path) -> Path | None:
        candidate = Path(file_str)
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        return candidate

    def _get_parser(self, language: str) -> Parser | None:
        if Parser is None or get_language is None:
            return None
        if language in self._disabled:
            return None
        parser = self._parsers.get(language)
        if parser is None:
            try:
                lang = get_language(language)
                parser = Parser()
                parser.set_language(lang)
                self._parsers[language] = parser
            except Exception:  # pragma: no cover - dependency issues
                self._disabled.add(language)
                self._parsers[language] = None
                return None
        return parser

    @lru_cache(maxsize=256)
    def _parse(self, language: str, path: Path, mtime_ns: int) -> _ParseResult | None:
        parser = self._get_parser(language)
        if parser is None:
            return None
        try:
            source = path.read_bytes()
        except (FileNotFoundError, OSError):
            return None
        tree = parser.parse(source)
        return _ParseResult(tree=tree, source=source)

    def _find_context(self, language: str, path: Path, line: int) -> str | None:
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            return None
        parsed = self._parse(language, path, mtime_ns)
        if parsed is not None:
            node = self._node_at(parsed.tree.root_node, parsed.source, line)
            if node is not None:
                if language == "python":
                    return self._python_context(node)
                if language == "markdown":
                    return self._markdown_context(node, parsed.source)
                if language == "json":
                    return self._json_context(node, parsed.source)
        # fallbacks when Tree-sitter unavailable
        if language == "python":
            return self._python_fallback(path, line)
        if language == "markdown":
            return self._markdown_fallback(path, line)
        if language == "json":
            return self._json_fallback(path, line)
        return None

    def _node_at(self, root: Node, source: bytes, line: int) -> Node | None:
        # Tree-sitter uses zero-based row
        target_row = max(line - 1, 0)
        node = root.descendant_for_point_range((target_row, 0), (target_row, 1000))
        if node is None:
            return None
        # climb to significant node
        while node.parent and node.type in {"block", "suite", "pair", "section"}:
            node = node.parent
        return node

    def _python_context(self, node: Node) -> str | None:
        while node:
            if node.type in {
                "function_definition",
                "class_definition",
                "async_function_definition",
            }:
                name_node = node.child_by_field_name("name")
                if name_node:
                    return name_node.text.decode("utf-8")
            node = node.parent
        return None

    def _markdown_context(self, node: Node, source: bytes) -> str | None:
        current = node
        while current:
            if current.type in {"atx_heading", "setext_heading"}:
                text = current.child_by_field_name("content")
                if text:
                    return text.text.decode("utf-8").strip()
            current = current.parent
        return None

    def _json_context(self, node: Node, source: bytes) -> str | None:
        path_parts: list[str] = []
        current = node
        while current:
            if current.type == "pair":
                key_node = current.child_by_field_name("key")
                if key_node:
                    key_text = key_node.text.decode("utf-8").strip('"')
                    path_parts.append(key_text)
            current = current.parent
        if not path_parts:
            return None
        return ".".join(reversed(path_parts))

    @staticmethod
    def _python_fallback(path: Path, line: int) -> str | None:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None
        best_node: ast.AST | None = None
        best_start = -1
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = getattr(node, "lineno", None)
                end = getattr(node, "end_lineno", start)
                if start is None or end is None:
                    continue
                if start <= line <= end and start >= best_start:
                    best_node = node
                    best_start = start
        if isinstance(best_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return best_node.name
        return None

    @staticmethod
    def _markdown_fallback(path: Path, line: int) -> str | None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        idx = min(max(line - 1, 0), len(lines) - 1)
        while idx >= 0:
            text = lines[idx].strip()
            if text.startswith("#"):
                return text.lstrip("#").strip()
            if text and idx > 0 and all(ch == text[0] for ch in text) and text[0] in "=-":
                heading = lines[idx - 1].strip()
                if heading:
                    return heading
            idx -= 1
        return None

    @staticmethod
    def _json_fallback(path: Path, line: int) -> str | None:
        # Simple heuristic: walk backwards to find enclosing key
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        idx = min(max(line - 1, 0), len(lines) - 1)
        stack: list[str] = []
        for i in range(idx, -1, -1):
            text = lines[i]
            stripped = text.strip()
            if stripped.startswith("}") or stripped.startswith("]"):
                if stack:
                    stack.pop()
                continue
            if stripped.startswith("\"") and ":" in stripped:
                key = stripped.split(":", 1)[0].strip().strip('"')
                stack.insert(0, key)
                break
        if stack:
            return ".".join(stack)
        return None


CONTEXT_RESOLVER = TreeSitterContextResolver()
