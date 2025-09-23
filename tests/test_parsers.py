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
    parse_checkmake,
    parse_cpplint,
    parse_dockerfilelint,
    parse_dotenv_linter,
    parse_eslint,
    parse_golangci_lint,
    parse_hadolint,
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
    parser = JsonParser(parse_yamllint)
    stdout = """
    [
      {
        "file": "configs/app.yaml",
        "problems": [
          {"line": 5, "column": 3, "message": "too many spaces after colon", "level": "warning", "rule": "colons"}
        ]
      }
    ]
    """
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
    assert first.severity.value == "warning"
    second = diags[1]
    assert second.code == "E011"
    assert second.severity.value == "error"


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
    assert diag.severity.value == "warning"


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
    assert diag.severity.value == "error"


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
    assert diag.severity.value == "error"
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
    assert diag.severity.value == "warning"


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


def test_parse_hadolint() -> None:
    parser = JsonParser(parse_hadolint)
    stdout = """
    [{"line": 3, "column": 1, "level": "error", "code": "DL3007", "message": "Using latest is prone to errors", "file": "Dockerfile"}]
    """
    diags = parser.parse(stdout, "", context=_ctx())
    assert len(diags) == 1
    diag = diags[0]
    assert diag.file == "Dockerfile"
    assert diag.code == "DL3007"
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
