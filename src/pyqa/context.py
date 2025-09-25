# SPDX-License-Identifier: MIT
"""Context extraction using Tree-sitter grammars."""

from __future__ import annotations

import ast
import importlib
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from .models import Diagnostic


def _build_parser_loader() -> Callable[[str], Any] | None:
    try:
        tree_sitter_module = importlib.import_module("tree_sitter")
    except ModuleNotFoundError:
        return None

    parser_cls = getattr(tree_sitter_module, "Parser", None)
    if parser_cls is None:
        return None

    try:
        bundled_get_parser = importlib.import_module("tree_sitter_languages").get_parser
    except ModuleNotFoundError:
        try:
            language_module = importlib.import_module("tree_sitter")
            language_cls = getattr(language_module, "Language", None)
        except (ModuleNotFoundError, AttributeError):
            return None

        def bundled_get_parser(name: str) -> Any:
            module_name = f"tree_sitter_{name.replace('-', '_')}"
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError:
                return None
            language_factory = getattr(module, "language", None)
            if language_factory is None:
                return None
            language = language_cls(language_factory()) if callable(language_cls) else None
            parser = parser_cls() if callable(parser_cls) else None
            if language is None or parser is None:
                return None
            setter = getattr(parser, "set_language", None)
            if callable(setter):
                setter(language)
            elif hasattr(parser, "language"):
                try:
                    parser.language = language  # type: ignore[assignment]
                except (AttributeError, TypeError, ValueError):
                    return None
            return parser

    return bundled_get_parser


_GET_PARSER = _build_parser_loader()


class _ParseResult(BaseModel):
    tree: Any
    source: bytes

    model_config = ConfigDict(arbitrary_types_allowed=True)


class TreeSitterContextResolver:
    """Enrich diagnostics with structural context using Tree-sitter."""

    _LANGUAGE_ALIASES: Final[dict[str, set[str]]] = {
        "python": {".py", ".pyi"},
        "markdown": {".md", ".markdown", ".mdx"},
        "json": {".json"},
        "javascript": {".js", ".jsx"},
        "typescript": {".ts", ".tsx"},
        "go": {".go"},
        "rust": {".rs"},
        "sql": {".sql"},
        "yaml": {".yaml", ".yml"},
        "shell": {".sh", ".bash", ".zsh"},
        "lua": {".lua"},
        "php": {".php", ".phtml"},
        "toml": {".toml"},
        "make": {".mk"},
    }

    _GRAMMAR_NAMES: Final[dict[str, str]] = {
        "python": "python",
        "markdown": "markdown",
        "json": "json",
        "javascript": "javascript",
        "typescript": "typescript",
        "go": "go",
        "rust": "rust",
        "sql": "sql",
        "yaml": "yaml",
        "shell": "bash",
        "lua": "lua",
        "php": "php",
        "toml": "toml",
        "dockerfile": "dockerfile",
        "make": "make",
    }

    _FALLBACK_LANGUAGES: Final[set[str]] = {"python", "markdown", "json"}

    def __init__(self) -> None:
        self._parsers: dict[str, Any | None] = {}
        self._disabled: set[str] = set()

    def grammar_modules(self) -> dict[str, str]:
        """Expose supported grammar modules for diagnostic tooling."""
        return dict(self._GRAMMAR_NAMES)

    def annotate(self, diagnostics: Iterable[Diagnostic], *, root: Path) -> None:
        root_path = root.resolve()
        for diag in diagnostics:
            if diag.function or diag.line is None or not diag.file:
                continue
            language = self._detect_language(diag.file)
            if language is None:
                continue
            location = self._resolve_path(diag.file, root_path)
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
        name = path.name.lower()
        if name in {"dockerfile", "containerfile"}:
            return "dockerfile"
        if name == "makefile":
            return "make"
        return None

    @staticmethod
    def _resolve_path(file_str: str, root: Path) -> Path | None:
        candidate = Path(file_str)
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        return candidate

    def _get_parser(self, language: str) -> Any | None:
        if language in self._disabled:
            return None
        cached = self._parsers.get(language)
        if cached is not None:
            return cached
        loader = self._resolve_parser_loader(language)
        if loader is None:
            return None
        try:
            parser = loader()
        except (ImportError, OSError, ValueError, RuntimeError):
            self._disable_language(language)
            return None
        if parser is None or not hasattr(parser, "parse"):
            self._disable_language(language)
            return None
        self._parsers[language] = parser
        return parser

    def _resolve_parser_loader(self, language: str) -> Callable[[], Any] | None:
        loader_fn = _GET_PARSER
        if loader_fn is None:
            self._disable_language(language)
            return None
        grammar_name = self._GRAMMAR_NAMES.get(language)
        if grammar_name is None:
            self._disable_language(language)
            return None

        def _loader() -> Any:
            return loader_fn(grammar_name) if loader_fn is not None else None

        return _loader

    def _disable_language(self, language: str) -> None:
        if language not in self._FALLBACK_LANGUAGES:
            self._disabled.add(language)
        self._parsers[language] = None

    @lru_cache(maxsize=256)
    def _parse(self, language: str, path: Path, _mtime_ns: int) -> _ParseResult | None:
        parser = self._get_parser(language)
        if parser is None:
            return None
        try:
            source = path.read_bytes()
        except (FileNotFoundError, OSError):
            return None
        try:
            tree = parser.parse(source)
        except (ValueError, RuntimeError):
            return None
        return _ParseResult(tree=tree, source=source)

    def _find_context(self, language: str, path: Path, line: int) -> str | None:
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            return None
        parsed = self._parse(language, path, mtime_ns)
        if parsed is not None:
            tree_context = self._context_from_parse(language, parsed, line)
            if tree_context:
                return tree_context
        return self._fallback_context(language, path, line)

    def _context_from_parse(self, language: str, parsed: _ParseResult, line: int) -> str | None:
        tree = getattr(parsed.tree, "root_node", None)
        if tree is None:
            return None
        if language == "python":
            return self._python_context(tree, line)
        if language == "markdown":
            return self._markdown_context(tree, line, parsed.source)
        if language == "json":
            node = self._node_at(tree, line)
            if node is not None:
                return self._json_context(node)
        return None

    def _fallback_context(self, language: str, path: Path, line: int) -> str | None:
        if language == "python":
            context = self._python_ast_context(path, line)
            return context or self._python_fallback(path, line)
        if language == "markdown":
            context = self._markdown_heading_context(path, line)
            return context or self._markdown_fallback(path, line)
        if language == "json":
            return self._json_fallback(path, line)
        return None

    def _python_context(self, node: Any, line: int) -> str | None:
        best_named_line = -1
        best_named_value: str | None = None
        best_generic_line = -1
        best_generic_node: Any | None = None
        stack = [node]
        while stack:
            current = stack.pop()
            start_point = getattr(current, "start_point", None)
            end_point = getattr(current, "end_point", None)
            children = getattr(current, "children", None)
            if not start_point or not end_point:
                if children:
                    stack.extend(child for child in children if child is not None)
                continue
            start_row = start_point[0] + 1
            end_row = end_point[0] + 1
            if start_row > line or line > end_row:
                if children:
                    stack.extend(child for child in children if child is not None)
                continue

            node_type = getattr(current, "type", "")
            if node_type in {"function_definition", "class_definition"}:
                name = self._node_name(current)
                if name and start_row >= best_named_line:
                    best_named_line = start_row
                    best_named_value = name

            if start_row >= best_generic_line:
                best_generic_line = start_row
                best_generic_node = current

            if children:
                stack.extend(child for child in children if child is not None)

        if best_named_value:
            return best_named_value
        if best_generic_node is None:
            return None
        fallback_name = self._node_name(best_generic_node)
        if fallback_name:
            return fallback_name
        node_type = getattr(best_generic_node, "type", None)
        return str(node_type) if node_type else None

    def _markdown_context(self, node: Any, line: int, source: bytes) -> str | None:
        heading = self._select_markdown_heading(node, line)
        if heading is None:
            return None
        return self._extract_markdown_heading(heading, source)

    def _select_markdown_heading(self, node: Any, line: int) -> Any | None:
        stack = [node]
        best_node: Any | None = None
        best_start = -1
        while stack:
            current = stack.pop()
            node_type = getattr(current, "type", "")
            if node_type.startswith("heading"):
                start_point = getattr(current, "start_point", None)
                if start_point and start_point[0] + 1 <= line and start_point[0] >= best_start:
                    best_node = current
                    best_start = start_point[0]
            children = getattr(current, "children", [])
            stack.extend(children)
        return best_node

    def _extract_markdown_heading(self, node: Any, source: bytes) -> str | None:
        text_node = getattr(node, "child_by_field_name", lambda _: None)("text")
        if text_node is None:
            return None
        start_byte = getattr(text_node, "start_byte", None)
        end_byte = getattr(text_node, "end_byte", None)
        if start_byte is None or end_byte is None:
            return None
        return source[start_byte:end_byte].decode("utf-8").strip()

    @staticmethod
    def _node_name(node: Any) -> str | None:
        extractor = getattr(node, "child_by_field_name", None)
        if callable(extractor):
            name_node = extractor("name")
            raw = getattr(name_node, "text", None)
            if isinstance(raw, bytes):
                return raw.decode("utf-8")
            if isinstance(raw, str):
                return raw
        text = getattr(node, "text", None)
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        if isinstance(text, str) and text.strip():
            return text.strip()
        return None

    def _markdown_heading_context(self, path: Path, line: int) -> str | None:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        best_line = -1
        best_heading: str | None = None
        for index, raw_line in enumerate(content.splitlines(), start=1):
            stripped = raw_line.strip()
            if stripped.startswith("#") and index <= line:
                if index >= best_line:
                    best_line = index
                    best_heading = stripped.lstrip("# ")
        return best_heading

    def _markdown_fallback(self, path: Path, line: int) -> str | None:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        lines = content.splitlines()
        if not 1 <= line <= len(lines):
            return None
        return lines[line - 1].strip() or None

    def _node_at(self, node: Any, line: int) -> Any | None:
        stack = [node]
        while stack:
            current = stack.pop()
            start_point = getattr(current, "start_point", None)
            end_point = getattr(current, "end_point", None)
            if not start_point or not end_point:
                continue
            if start_point[0] + 1 <= line <= end_point[0] + 1:
                children = getattr(current, "children", None)
                if children:
                    stack.extend(children)
                    continue
                return current
        return None

    @staticmethod
    def _json_context(node: Any) -> str | None:
        node_type = getattr(node, "type", None)
        if node_type in {"pair", "object", "array"}:
            key_node = getattr(node, "child_by_field_name", lambda _: None)("key")
            if key_node is not None and hasattr(key_node, "text"):
                return key_node.text.decode("utf-8")
        return node_type if isinstance(node_type, str) else None

    def _json_fallback(self, path: Path, line: int) -> str | None:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        for index, raw_line in enumerate(content.splitlines(), start=1):
            if index == line:
                return raw_line.strip() or None
        return None

    def _python_ast_context(self, path: Path, line: int) -> str | None:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            return None
        best_node: ast.AST | None = None
        best_start = -1
        for node in ast.walk(tree):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)
            if start is None or end is None:
                continue
            if start <= line <= end:
                if start >= best_start:
                    best_node = node
                    best_start = start
        if isinstance(best_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return best_node.name
        return None

    @staticmethod
    def _python_fallback(path: Path, line: int) -> str | None:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        lines = content.splitlines()
        if not 1 <= line <= len(lines):
            return None
        raw = lines[line - 1].strip()
        return raw or None


CONTEXT_RESOLVER = TreeSitterContextResolver()

__all__ = ["CONTEXT_RESOLVER", "TreeSitterContextResolver"]
