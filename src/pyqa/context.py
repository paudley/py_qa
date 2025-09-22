"""Context extraction using Tree-sitter grammars."""

from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

try:  # pragma: no cover - optional dependency gating
    from tree_sitter import Language, Node, Parser  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - graceful degradation
    Parser = None  # type: ignore[assignment]
    Node = object  # type: ignore[misc]

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
        "javascript": {".js", ".jsx", ".ts", ".tsx"},
        "go": {".go"},
        "rust": {".rs"},
    }

    _GRAMMAR_MODULES = {
        "python": "tree_sitter_python",
        "markdown": "tree_sitter_markdown",
        "json": "tree_sitter_json",
        "javascript": "tree_sitter_javascript",
        "go": "tree_sitter_go",
        "rust": "tree_sitter_rust",
    }

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
        if Parser is None:
            return None
        if language in self._disabled:
            return None
        parser = self._parsers.get(language)
        if parser is None:
            module_name = self._GRAMMAR_MODULES.get(language)
            if module_name is None:
                self._disabled.add(language)
                self._parsers[language] = None
                return None
            try:
                module = importlib.import_module(module_name)
                lang = Language(module.language())  # type: ignore[attr-defined]
                parser = Parser()
                parser.language = lang  # type: ignore[assignment]
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
            if language == "python":
                context = self._python_context(parsed.tree.root_node, line)
                if context:
                    return context
            elif language == "markdown":
                context = self._markdown_context(
                    parsed.tree.root_node, line, parsed.source
                )
                if context:
                    return context
            elif language == "json":
                node = self._node_at(parsed.tree.root_node, line)
                if node is not None:
                    context = self._json_context(node)
                    if context:
                        return context
        # fallbacks when Tree-sitter unavailable
        if language == "python":
            return self._python_fallback(path, line)
        if language == "markdown":
            return self._markdown_fallback(path, line)
        if language == "json":
            return self._json_fallback(path, line)
        return None

    def _node_at(self, root: Node, line: int) -> Node | None:
        target_row = max(line - 1, 0)
        return root.descendant_for_point_range((target_row, 0), (target_row, 1000))

    def _python_context(self, root: Node, line: int) -> str | None:
        target_row = line - 1
        best: tuple[int, Node] | None = None
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in {
                "function_definition",
                "class_definition",
                "async_function_definition",
            }:
                start = node.start_point[0]
                end = node.end_point[0]
                if start <= target_row <= end:
                    if best is None or start >= best[0]:
                        best = (start, node)
            stack.extend(node.children)
        if best is None:
            return None
        name_node = best[1].child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8")
        return None

    def _markdown_context(self, root: Node, line: int, source: bytes) -> str | None:
        target_row = line - 1
        stack = [root]
        candidate: Node | None = None
        candidate_start = -1
        while stack:
            node = stack.pop()
            if node.type in {"atx_heading", "setext_heading"}:
                start = node.start_point[0]
                end = node.end_point[0]
                if start <= target_row <= end:
                    if candidate is None or start >= candidate_start:
                        candidate = node
                        candidate_start = start
            if node.type == "section":
                for child in node.children:
                    if child.type in {"atx_heading", "setext_heading"}:
                        start = child.start_point[0]
                        end = child.end_point[0]
                        if start <= target_row:
                            if candidate is None or start >= candidate_start:
                                candidate = child
                                candidate_start = start
            stack.extend(node.children)
        if candidate is None:
            return None
        text_node = candidate.child_by_field_name("heading_content")
        if text_node:
            return text_node.text.decode("utf-8").strip()
        inline = candidate.child_by_field_name("content")
        if inline:
            return inline.text.decode("utf-8").strip()
        return None

    def _json_context(self, node: Node) -> str | None:
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
            if (
                text
                and idx > 0
                and all(ch == text[0] for ch in text)
                and text[0] in "=-"
            ):
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
            if stripped.startswith('"') and ":" in stripped:
                key = stripped.split(":", 1)[0].strip().strip('"')
                stack.insert(0, key)
                break
        if stack:
            return ".".join(stack)
        return None


CONTEXT_RESOLVER = TreeSitterContextResolver()
