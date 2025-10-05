# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Context extraction using Tree-sitter grammars."""

from __future__ import annotations

import ast
import importlib
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from .models import Diagnostic


class _ParseResult(BaseModel):
    tree: Any
    source: bytes

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Language(str, Enum):
    """Enumerate languages supported by the context resolver."""

    PYTHON = "python"
    MARKDOWN = "markdown"
    JSON = "json"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    SQL = "sql"
    YAML = "yaml"
    SHELL = "shell"
    LUA = "lua"
    PHP = "php"
    TOML = "toml"
    DOCKERFILE = "dockerfile"
    MAKE = "make"


@dataclass(frozen=True)
class ParserFactory:
    """Factory capable of constructing tree-sitter parsers on demand."""

    parser_cls: Callable[[], Any] | None
    get_parser: Callable[[str], Any] | None
    language_cls: type[Any] | None

    def create(self, grammar_name: str) -> Any | None:
        """Return an initialised parser for ``grammar_name`` when possible."""

        if self.get_parser is not None:
            return self.get_parser(grammar_name)
        if self.language_cls is None:
            return None
        module_name = f"tree_sitter_{grammar_name.replace('-', '_')}"
        module = self._import_language_module(module_name)
        if module is None:
            return None
        language = self._build_language(module)
        parser = self._build_parser()
        if language is None or parser is None:
            return None
        return self._assign_language(parser, language)

    def _build_language(self, module: Any) -> Any | None:
        """Return a language object constructed from ``module`` when possible."""

        language_factory = getattr(module, "language", None)
        if not callable(language_factory) or not callable(self.language_cls):
            return None
        try:
            return self.language_cls(language_factory())
        except (TypeError, ValueError):
            return None

    def _build_parser(self) -> Any | None:
        """Return a fresh parser instance when available."""

        parser_factory = self.parser_cls
        if parser_factory is None:
            return None
        try:
            return parser_factory()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _import_language_module(module_name: str) -> Any | None:
        """Import the Tree-sitter language module if present."""

        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError:
            return None

    @staticmethod
    def _assign_language(parser: Any, language: Any) -> Any | None:
        """Attach ``language`` to ``parser`` returning the parser or ``None``."""

        setter = getattr(parser, "set_language", None)
        if callable(setter):
            setter(language)
            return parser
        if hasattr(parser, "language"):
            try:
                setattr(parser, "language", language)
            except (AttributeError, TypeError, ValueError):
                return None
            return parser
        return None


def _build_parser_loader() -> ParserFactory | None:
    """Return a parser factory when tree-sitter bindings are available."""

    tree_sitter_module = importlib.import_module("tree_sitter")
    parser_cls = getattr(tree_sitter_module, "Parser", None)
    if parser_cls is None:
        raise RuntimeError(
            "tree_sitter.Parser is unavailable; upgrade the tree-sitter package",
        )

    language_cls = getattr(tree_sitter_module, "Language", None)

    try:
        bundled = importlib.import_module("tree_sitter_languages")
    except ModuleNotFoundError:
        if language_cls is None:
            return None
        return ParserFactory(parser_cls=parser_cls, get_parser=None, language_cls=language_cls)

    get_parser = getattr(bundled, "get_parser", None)
    if not callable(get_parser):
        raise RuntimeError(
            "tree_sitter_languages.get_parser is unavailable; reinstall tree-sitter-languages",
        )
    return ParserFactory(parser_cls=parser_cls, get_parser=get_parser, language_cls=language_cls)


_PARSER_FACTORY = _build_parser_loader()


class TreeSitterContextResolver:
    """Enrich diagnostics with structural context using Tree-sitter."""

    _LANGUAGE_ALIASES: Final[dict[Language, tuple[str, ...]]] = {
        Language.PYTHON: (".py", ".pyi"),
        Language.MARKDOWN: (".md", ".markdown", ".mdx"),
        Language.JSON: (".json",),
        Language.JAVASCRIPT: (".js", ".jsx"),
        Language.TYPESCRIPT: (".ts", ".tsx"),
        Language.GO: (".go",),
        Language.RUST: (".rs",),
        Language.SQL: (".sql",),
        Language.YAML: (".yaml", ".yml"),
        Language.SHELL: (".sh", ".bash", ".zsh"),
        Language.LUA: (".lua",),
        Language.PHP: (".php", ".phtml"),
        Language.TOML: (".toml",),
        Language.MAKE: (".mk",),
    }

    _SPECIAL_FILENAMES: Final[dict[str, Language]] = {
        "dockerfile": Language.DOCKERFILE,
        "containerfile": Language.DOCKERFILE,
        "makefile": Language.MAKE,
    }

    _GRAMMAR_NAMES: Final[dict[Language, str]] = {
        Language.PYTHON: "python",
        Language.MARKDOWN: "markdown",
        Language.JSON: "json",
        Language.JAVASCRIPT: "javascript",
        Language.TYPESCRIPT: "typescript",
        Language.GO: "go",
        Language.RUST: "rust",
        Language.SQL: "sql",
        Language.YAML: "yaml",
        Language.SHELL: "bash",
        Language.LUA: "lua",
        Language.PHP: "php",
        Language.TOML: "toml",
        Language.DOCKERFILE: "dockerfile",
        Language.MAKE: "make",
    }

    _FALLBACK_LANGUAGES: Final[set[Language]] = {
        Language.PYTHON,
        Language.MARKDOWN,
        Language.JSON,
    }

    def __init__(self) -> None:
        self._parsers: dict[Language, Any] = {}
        self._disabled: set[Language] = set()

    def grammar_modules(self) -> dict[str, str]:
        """Expose supported grammar modules for diagnostic tooling."""
        return {language.value: name for language, name in self._GRAMMAR_NAMES.items()}

    def annotate(self, diagnostics: Iterable[Diagnostic], *, root: Path) -> None:
        """Populate ``diagnostic.function`` using structural context when available.

        Args:
            diagnostics: Iterable of diagnostics requiring contextual enrichment.
            root: Repository root used to resolve relative file paths.

        """

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

    def resolve_context_for_lines(
        self,
        file_path: str,
        *,
        root: Path,
        lines: Iterable[int],
    ) -> dict[int, str]:
        """Return context strings for the requested ``lines``.

        Args:
            file_path: File containing the diagnostics.
            root: Repository root directory for resolving ``file_path``.
            lines: Line numbers that require contextual names.

        Returns:
            Mapping of line number to resolved context string.

        """

        language = self._detect_language(file_path)
        if language is None:
            return {}
        location = self._resolve_path(file_path, root)
        if location is None or not location.is_file():
            return {}

        contexts: dict[int, str] = {}
        for line in lines:
            if line in contexts:
                continue
            context = self._find_context(language, location, line)
            if context:
                contexts[line] = context
        return contexts

    def _detect_language(self, file_str: str) -> Language | None:
        """Return the language associated with ``file_str`` when known."""

        path = Path(file_str)
        suffix = path.suffix.lower()
        for language, suffixes in self._LANGUAGE_ALIASES.items():
            if suffix in suffixes:
                return language
        name = path.name.lower()
        return self._SPECIAL_FILENAMES.get(name)

    @staticmethod
    def _resolve_path(file_str: str, root: Path) -> Path | None:
        candidate = Path(file_str)
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        return candidate

    def _get_parser(self, language: Language) -> Any | None:
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

    def _resolve_parser_loader(self, language: Language) -> Callable[[], Any] | None:
        factory = _PARSER_FACTORY
        if factory is None:
            self._disable_language(language)
            return None
        grammar_name = self._GRAMMAR_NAMES.get(language)
        if grammar_name is None:
            self._disable_language(language)
            return None

        parser_factory = factory

        def _loader() -> Any:
            return parser_factory.create(grammar_name)

        return _loader

    def _disable_language(self, language: Language) -> None:
        if language not in self._FALLBACK_LANGUAGES:
            self._disabled.add(language)
        self._parsers.pop(language, None)

    @lru_cache(maxsize=256)
    def _parse(self, language: Language, path: Path, _mtime_ns: int) -> _ParseResult | None:
        parser = self._get_parser(language)
        if parser is None:
            return None
        try:
            source = path.read_bytes()
        except OSError:
            return None
        try:
            tree = parser.parse(source)
        except (ValueError, RuntimeError):
            return None
        return _ParseResult(tree=tree, source=source)

    def _find_context(self, language: Language, path: Path, line: int) -> str | None:
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

    def _context_from_parse(
        self,
        language: Language,
        parsed: _ParseResult,
        line: int,
    ) -> str | None:
        tree = getattr(parsed.tree, "root_node", None)
        if tree is None:
            return None
        if language is Language.PYTHON:
            return self._python_context(tree, line)
        if language is Language.MARKDOWN:
            return self._markdown_context(tree, line, parsed.source)
        if language is Language.JSON:
            node = self._node_at(tree, line)
            if node is not None:
                return self._json_context(node)
        return None

    def _fallback_context(self, language: Language, path: Path, line: int) -> str | None:
        if language is Language.PYTHON:
            context = self._python_ast_context(path, line)
            return context or self._python_fallback(path, line)
        if language is Language.MARKDOWN:
            context = self._markdown_heading_context(path, line)
            return context or self._markdown_fallback(path, line)
        if language is Language.JSON:
            return self._json_fallback(path, line)
        return None

    def _python_context(self, node: Any, line: int) -> str | None:
        """Return the most specific Python scope covering ``line``."""

        named_scope = _nearest_python_named_scope(node, line)
        if named_scope:
            return named_scope
        generic_node = _nearest_python_generic_node(node, line)
        if generic_node is None:
            return None
        fallback_name = _tree_node_name(generic_node)
        if fallback_name:
            return fallback_name
        node_type = getattr(generic_node, "type", None)
        return str(node_type) if isinstance(node_type, str) else None

    def _markdown_context(self, node: Any, line: int, source: bytes) -> str | None:
        """Return the Markdown heading that precedes ``line`` when available."""

        heading = self._select_markdown_heading(node, line)
        if heading is None:
            return None
        return self._extract_markdown_heading(heading, source)

    def _select_markdown_heading(self, node: Any, line: int) -> Any | None:
        best_node: Any | None = None
        best_start = -1
        for current in _iter_tree_nodes(node):
            node_type = getattr(current, "type", "")
            if not node_type.startswith("heading"):
                continue
            start_row, _ = _node_row_span(current)
            if start_row is None or start_row > line or start_row < best_start:
                continue
            best_start = start_row
            best_node = current
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
        best_node: Any | None = None
        best_depth = -1
        for current, depth in _iter_tree_nodes_with_depth(node):
            if not _node_contains_line(current, line):
                continue
            if depth >= best_depth:
                best_depth = depth
                best_node = current
        return best_node

    @staticmethod
    def _json_context(node: Any) -> str | None:
        node_type = getattr(node, "type", None)
        if node_type in {"pair", "object", "array"}:
            key_node = getattr(node, "child_by_field_name", lambda _: None)("key")
            if key_node is not None:
                text_attr = getattr(key_node, "text", None)
                if isinstance(text_attr, bytes):
                    return text_attr.decode("utf-8")
                if isinstance(text_attr, str):
                    return text_attr
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


def _tree_node_name(node: Any) -> str | None:
    """Return a normalised display name for ``node`` when available."""

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


def _iter_tree_nodes(node: Any) -> Iterator[Any]:
    """Yield nodes in depth-first order starting from ``node``."""

    yield node
    children = getattr(node, "children", None)
    if not children:
        return
    for child in children:
        if child is not None:
            yield from _iter_tree_nodes(child)


def _iter_tree_nodes_with_depth(node: Any, depth: int = 0) -> Iterator[tuple[Any, int]]:
    """Yield nodes and their depth in depth-first order."""

    yield node, depth
    children = getattr(node, "children", None)
    if not children:
        return
    for child in children:
        if child is not None:
            yield from _iter_tree_nodes_with_depth(child, depth + 1)


def _node_row_span(node: Any) -> tuple[int | None, int | None]:
    """Return 1-based (start, end) line numbers for ``node`` when available."""

    start_point = getattr(node, "start_point", None)
    end_point = getattr(node, "end_point", None)
    start_row = start_point[0] + 1 if start_point else None
    end_row = end_point[0] + 1 if end_point else None
    return start_row, end_row


def _node_contains_line(node: Any, line: int) -> bool:
    """Return ``True`` when ``node`` spans ``line``."""

    start_row, end_row = _node_row_span(node)
    return bool(start_row is not None and end_row is not None and start_row <= line <= end_row)


def _nearest_python_named_scope(node: Any, line: int) -> str | None:
    """Return the innermost named Python scope covering ``line``."""

    best_line = -1
    best_name: str | None = None
    for current in _iter_tree_nodes(node):
        node_type = getattr(current, "type", "")
        if node_type not in {"function_definition", "class_definition"}:
            continue
        if not _node_contains_line(current, line):
            continue
        start_row, _ = _node_row_span(current)
        if start_row is None or start_row < best_line:
            continue
        name = _tree_node_name(current)
        if name:
            best_line = start_row
            best_name = name
    return best_name


def _nearest_python_generic_node(node: Any, line: int) -> Any | None:
    """Return the deepest node covering ``line`` when no named scope exists."""

    best_node: Any | None = None
    best_line = -1
    for current in _iter_tree_nodes(node):
        if not _node_contains_line(current, line):
            continue
        start_row, _ = _node_row_span(current)
        if start_row is None or start_row < best_line:
            continue
        best_line = start_row
        best_node = current
    return best_node


CONTEXT_RESOLVER = TreeSitterContextResolver()

__all__ = ["CONTEXT_RESOLVER", "TreeSitterContextResolver"]
