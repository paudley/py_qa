# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests covering parser adapters for supported tools."""

# pylint: disable=missing-function-docstring

from pathlib import Path

from pyqa.config import Config
from pyqa.models import RawDiagnostic
from pyqa.parsers import (
    JsonParser,
    TextParser,
    parse_actionlint,
    parse_bandit,
    parse_cargo_clippy,
    parse_eslint,
    parse_golangci_lint,
    parse_mypy,
    parse_pylint,
    parse_pyright,
    parse_ruff,
    parse_tsc,
)
from pyqa.severity import Severity
from pyqa.tools.base import ToolContext


def _ctx() -> ToolContext:
    return ToolContext(cfg=Config(), root=Path("."), files=(), settings={})


def test_parse_ruff() -> None:
    parser = JsonParser(parse_ruff)
    stdout = """
    [
      {"code": "F401", "message": "unused import", "filename": "pkg/mod.py", "location": {"row": 1, "column": 1}}
    ]
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert isinstance(diag, RawDiagnostic)
    assert diag.file == "pkg/mod.py"
    assert diag.code == "F401"


def test_parse_pylint() -> None:
    parser = JsonParser(parse_pylint)
    stdout = """
    [{"type": "warning", "message": "issue", "path": "pkg/app.py", "line": 2, "column": 4, "message-id": "W0101"}]
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    assert diags[0].code == "W0101"


def test_parse_pyright() -> None:
    parser = JsonParser(parse_pyright)
    stdout = """
    {"generalDiagnostics": [{"file": "pkg/app.py", "message": "problem", "severity": "error", "range": {"start": {"line": 3, "character": 1}}}]}
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    severity = diags[0].severity
    assert isinstance(severity, Severity)
    assert severity.value == "error"


def test_parse_mypy() -> None:
    parser = JsonParser(parse_mypy)
    stdout = """
    [{"path": "pkg/app.py", "line": 10, "column": 1, "message": "oops", "severity": "note", "name": "pkg.app.check_func", "code": "assignment"}]
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    severity = diags[0].severity
    assert isinstance(severity, Severity)
    assert severity.value == "note"
    assert diags[0].function == "check_func"
    assert diags[0].code == "assignment"
    assert diags[0].tool == "mypy"


def test_parse_actionlint() -> None:
    parser = JsonParser(parse_actionlint)
    stdout = """
    [{"path": ".github/workflows/ci.yml", "line": 12, "column": 4, "message": "failure", "severity": "error", "kind": "shellcheck"}]
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == ".github/workflows/ci.yml"
    assert diag.line == 12
    assert diag.code == "shellcheck"
    assert diag.tool == "actionlint"


def test_parse_bandit() -> None:
    parser = JsonParser(parse_bandit)
    stdout = """
    {"results": [{"filename": "pkg/app.py", "line_number": 5, "issue_text": "risk", "issue_severity": "HIGH", "test_id": "B101"}]}
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    severity = diags[0].severity
    assert isinstance(severity, Severity)
    assert severity.value == "error"


def test_parse_eslint() -> None:
    parser = JsonParser(parse_eslint)
    stdout = """
    [{"filePath": "pkg/app.ts", "messages": [{"line": 4, "column": 2, "message": "oops", "ruleId": "no-console", "severity": 2}]}]
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.tool == "eslint"
    severity = diag.severity
    assert isinstance(severity, Severity)
    assert severity.value == "error"


def test_parse_tsc() -> None:
    parser = TextParser(parse_tsc)
    stdout = "pkg/app.ts(5,10): error TS2304: Cannot find name 'foo'.\n"
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.code == "TS2304"
    severity = diag.severity
    assert isinstance(severity, Severity)
    assert severity.value == "error"


def test_parse_golangci_lint() -> None:
    parser = JsonParser(parse_golangci_lint)
    stdout = """
    {"Issues": [{"FromLinter": "govet", "Text": "bad", "Pos": {"Filename": "main.go", "Line": 5, "Column": 3}, "Severity": "warning"}]}
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "main.go"
    severity = diag.severity
    assert isinstance(severity, Severity)
    assert severity.value == "warning"


def test_parse_cargo_clippy() -> None:
    parser = JsonParser(parse_cargo_clippy)
    stdout = """
    {"reason":"compiler-message","message":{"level":"error","message":"issue","code":{"code":"E0001"},"spans":[{"file_name":"src/lib.rs","line_start":2,"column_start":1,"is_primary":true}]}}
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "src/lib.rs"
    assert diag.code == "E0001"
