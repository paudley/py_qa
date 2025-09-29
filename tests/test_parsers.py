# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Tests covering parser adapters for supported tools."""

from pathlib import Path

import pytest

from pyqa.config import Config
from pyqa.models import RawDiagnostic
from pyqa.parsers import (
    JsonParser,
    TextParser,
    parse_actionlint,
    parse_cargo_clippy,
    parse_checkmake,
    parse_cpplint,
    parse_dockerfilelint,
    parse_dotenv_linter,
    parse_eslint,
    parse_golangci_lint,
    parse_kube_linter,
    parse_luacheck,
    parse_lualint,
    parse_mypy,
    parse_perlcritic,
    parse_phplint,
    parse_pylint,
    parse_pyright,
    parse_remark,
    parse_ruff,
    parse_selene,
    parse_shfmt,
    parse_speccy,
    parse_sqlfluff,
    parse_stylelint,
    parse_tombi,
    parse_tsc,
    parse_yamllint,
)
from pyqa.severity import Severity
from pyqa.tooling.strategies import parser_json_diagnostics
from pyqa.tools.base import ToolContext


def _ctx() -> ToolContext:
    return ToolContext(cfg=Config(), root=Path(), files=(), settings={})


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


def test_parse_sqlfluff() -> None:
    parser = JsonParser(parse_sqlfluff)
    stdout = """
    [{"filepath": "queries/report.sql", "violations": [{"line_no": 4, "line_pos": 10, "description": "lint issue", "code": "L001", "severity": "error"}]}]
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "queries/report.sql"
    assert diag.code == "L001"
    assert diag.line == 4
    assert diag.column == 10
    assert diag.tool == "sqlfluff"


def test_parse_selene() -> None:
    parser = JsonParser(parse_selene)
    stdout = """
    {"type":"Diagnostic","severity":"Warning","code":"shadowing","message":"shadowing variable","primary_label":{"filename":"script.lua","span":{"start_line":1,"start_column":5}},"notes":["previous definition"],"secondary_labels":[{"message":"earlier assignment"}]}
    {"type":"Summary","errors":0,"warnings":1,"parse_errors":0}
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "script.lua"
    assert diag.line == 2
    assert diag.column == 6
    assert diag.code == "shadowing"
    assert "earlier assignment" in diag.message
    assert diag.tool == "selene"


def test_parse_kube_linter() -> None:
    parser = JsonParser(parse_kube_linter)
    stdout = """
    {
      "Reports": [
        {
          "Check": "run-as-non-root",
          "Diagnostic": {"Message": "Container must run as non-root"},
          "Object": {"Metadata": {"FilePath": "deployments/api.yaml"}}
        }
      ]
    }
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "deployments/api.yaml"
    assert diag.code == "run-as-non-root"
    assert diag.tool == "kube-linter"
    severity = diag.severity
    assert isinstance(severity, Severity)
    assert severity.value == "error"


def test_parse_cpplint() -> None:
    parser = TextParser(parse_cpplint)
    stdout = """foo.cc:10:  Extra space at end of line  [whitespace/indent] [3]
Done processing foo.cc
Total errors found: 1
"""
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "foo.cc"
    assert diag.line == 10
    assert diag.code == "whitespace/indent"
    assert diag.tool == "cpplint"


def test_parser_json_diagnostics_bandit() -> None:
    parser = parser_json_diagnostics(
        {
            "path": "results[*]",
            "mappings": {
                "file": "filename",
                "line": "line_number",
                "code": "test_id",
                "message": "issue_text",
                "severity": {
                    "path": "issue_severity",
                    "map": {"low": "notice", "medium": "warning", "high": "error"},
                    "default": "warning",
                },
                "tool": {"value": "bandit"},
            },
        }
    )
    stdout = """
    {"results": [{"filename": "pkg/app.py", "line_number": 5, "issue_text": "risk", "issue_severity": "HIGH", "test_id": "B101"}]}
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "pkg/app.py"
    assert diag.line == 5
    assert diag.code == "B101"
    assert diag.tool == "bandit"
    severity = diag.severity
    assert isinstance(severity, str)
    assert severity == "error"


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


def test_parse_stylelint() -> None:
    parser = JsonParser(parse_stylelint)
    stdout = """
    [
      {
        "source": "styles/base.css",
        "warnings": [
          {"line": 3, "column": 5, "text": "Unexpected unknown at-rule", "rule": "at-rule-no-unknown", "severity": "error"}
        ]
      }
    ]
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "styles/base.css"
    assert diag.code == "at-rule-no-unknown"
    severity = diag.severity
    assert isinstance(severity, Severity)
    assert severity.value == "error"


def test_parse_yamllint() -> None:
    parser = TextParser(parse_yamllint)
    stdout = "configs/app.yaml:5:3: [warning] too many spaces after colon (colons)"
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "configs/app.yaml"
    assert diag.code == "colons"
    severity = diag.severity
    assert isinstance(severity, Severity)
    assert severity.value == "warning"


def test_parse_dockerfilelint() -> None:
    parser = JsonParser(parse_dockerfilelint)
    stdout = """
    {
      "files": [
        {
          "file": "Dockerfile",
          "issues_count": 1,
          "issues": [
            {"line": 2, "category": "Clarity", "title": "Avoid latest", "description": "Pin versions"}
          ]
        }
      ],
      "totalIssues": 1
    }
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "Dockerfile"
    assert diag.code == "Clarity"
    assert diag.line == 2
    assert "Avoid latest" in diag.message


def test_parse_luacheck() -> None:
    parser = TextParser(parse_luacheck)
    stdout = """
    lib/module.lua:10:5: (W113) unused argument x
    lib/module.lua:12:1: (E011) expected assignment or function call
    Total: 1 warning / 1 error in 1 file
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 2
    first = diags[0]
    assert first.code == "W113"
    first_severity = first.severity
    assert isinstance(first_severity, Severity)
    assert first_severity.value == "warning"
    second = diags[1]
    assert second.code == "E011"
    second_severity = second.severity
    assert isinstance(second_severity, Severity)
    assert second_severity.value == "error"


def test_parse_lualint() -> None:
    parser = TextParser(parse_lualint)
    stdout = """
    src/example.lua:4: *** global SET of realy_aborting
    src/example.lua:5: global get of abortt
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 2
    first = diags[0]
    assert first.file == "src/example.lua"
    assert first.line == 4
    assert "SET of realy_aborting" in first.message


def test_parse_dotenv_linter() -> None:
    parser = TextParser(parse_dotenv_linter)
    stdout = """
    .env:3 LowercaseKey: The key should be uppercase
    .env:5 LeadingSpace: Unexpected leading space
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 2
    assert diags[0].code == "LowercaseKey"
    assert diags[1].code == "LeadingSpace"


def test_parse_remark() -> None:
    parser = JsonParser(parse_remark)
    stdout = """
    [
      {
        "name": "README.md",
        "messages": [
          {"reason": "List item spacing", "line": 4, "column": 3, "ruleId": "list-item-spacing", "fatal": false}
        ]
      }
    ]
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "README.md"
    assert diag.code == "list-item-spacing"
    severity = diag.severity
    assert isinstance(severity, Severity)
    assert severity.value == "warning"


def test_parse_speccy() -> None:
    parser = JsonParser(parse_speccy)
    stdout = """
    {
      "files": [
        {
          "file": "openapi.yaml",
          "issues": [
            {"message": "Path must start with a slash", "location": ["paths", "users"], "type": "error", "code": "path-slash"}
          ]
        }
      ],
      "total": 1
    }
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "openapi.yaml"
    assert "paths/users" in diag.message
    severity = diag.severity
    assert isinstance(severity, Severity)
    assert severity.value == "error"


def test_parse_shfmt() -> None:
    parser = TextParser(parse_shfmt)
    stdout = """
    diff -u a/script.sh b/script.sh
    --- a/script.sh
    +++ b/script.sh
    @@
    -echo  foo
    +echo foo
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.tool == "shfmt"
    assert "shfmt" in diag.message.lower()


def test_parse_phplint() -> None:
    parser = TextParser(parse_phplint)
    stdout = "Parse error: syntax error, unexpected ';' in src/index.php on line 14\n"
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "src/index.php"
    assert diag.line == 14
    severity = diag.severity
    assert isinstance(severity, Severity)
    assert severity.value == "error"
    assert diag.tool == "phplint"


def test_parse_tombi() -> None:
    parser = TextParser(parse_tombi)
    stdout = (
        "\x1b[1;31m  Error\x1b[0m: invalid key\n"
        "    at config.toml:2:4\n"
        "  Warning: missing value\n"
        "    at config.toml:5:1\n"
        "1 file failed to be linted\n"
    )
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 2
    first, second = diags
    assert first.severity == Severity.ERROR
    assert first.file == "config.toml"
    assert first.line == 2
    assert first.column == 4
    assert first.tool == "tombi"
    assert second.severity == Severity.WARNING
    assert second.line == 5


def test_parse_perlcritic() -> None:
    parser = TextParser(parse_perlcritic)
    stdout = "lib/Foo.pm:12:8:ProhibitUnusedVariables: MyVar is never used (ProhibitUnusedVariables)\n"
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "lib/Foo.pm"
    assert diag.line == 12
    assert diag.column == 8
    assert diag.code == "ProhibitUnusedVariables"


def test_parse_checkmake() -> None:
    parser = JsonParser(parse_checkmake)
    stdout = """
    {
      "files": [
        {
          "file": "Makefile",
          "errors": [
            {"line": 12, "column": 1, "message": "Target has no help text", "rule": "missing-help-text"}
          ]
        }
      ]
    }
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "Makefile"
    assert diag.code == "missing-help-text"
    severity = diag.severity
    assert isinstance(severity, Severity)
    assert severity.value == "warning"


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


def test_parser_json_diagnostics() -> None:
    parser = parser_json_diagnostics(
        {
            "mappings": {
                "file": "file",
                "line": "line",
                "column": "column",
                "code": "code",
                "message": "message",
                "severity": {
                    "path": "level",
                    "map": {"info": "notice", "warning": "warning", "error": "error"},
                    "default": "warning",
                },
            }
        }
    )
    stdout = """
    [{"line": 3, "column": 1, "level": "error", "code": "DL3007", "message": "Using latest is prone to errors", "file": "Dockerfile"}]
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "Dockerfile"
    assert diag.code == "DL3007"
    assert diag.column == 1
    severity = diag.severity
    assert isinstance(severity, str)
    assert severity == "error"


def test_parser_json_diagnostics_with_path_and_defaults() -> None:
    parser = parser_json_diagnostics(
        {
            "path": "items[*].diagnostics[*]",
            "inputFormat": "json-lines",
            "mappings": {
                "file": {"path": "location.file"},
                "line": {"path": "location.position.line"},
                "column": {"path": "location.position.column"},
                "code": {"path": "code"},
                "message": {"path": "message"},
                "severity": {"path": "level", "map": {"warning": "warning"}, "default": "notice"},
                "tool": {"value": "custom"},
            },
        }
    )

    stdout = """
    {"items": [{"diagnostics": [{"location": {"file": "foo.py", "position": {"line": "5", "column": 9}}, "level": "Warning", "code": "E100", "message": "Issue"}]}]}
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "foo.py"
    assert diag.line == 5
    assert diag.column == 9
    assert diag.code == "E100"
    assert diag.tool == "custom"
    severity = diag.severity
    assert isinstance(severity, str)
    assert severity == "warning"


def test_parser_json_diagnostics_missing_message_mapping() -> None:
    with pytest.raises(Exception) as excinfo:
        parser_json_diagnostics({"mappings": {"code": "id"}})

    assert "missing required field mapping" in str(excinfo.value)


def test_parse_golangci_lint() -> None:
    parser = JsonParser(parse_golangci_lint)
    stdout = """
    {"Issues": [{"FromLinter": "govet", "Text": "bad", "Pos": {"Filename": "main.go", "Line": 5, "Column": 3}, "Severity": "warning"}]}
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "main.go"
    assert diag.tool == "govet"
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
