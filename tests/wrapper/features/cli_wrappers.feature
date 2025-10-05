Feature: CLI launcher behaviour

  Background:
    Given the project root is set to the current repository

  Scenario: Local interpreter is used when probe succeeds
    Given the repository virtualenv is available
    When I run the "lint" wrapper with "--help"
    Then the wrapper exits with status 0
    And the wrapper uses the local interpreter

  Scenario: Fallback to uv when explicit interpreter is too old
    Given PYQA_PYTHON points to "artifacts/fake_py311.py"
    And PYQA_UV points to "artifacts/fake_uv.sh"
    When I run the "lint" wrapper with "--help"
    Then the wrapper exits with status 0
    And the wrapper falls back to uv

  Scenario: Failing when uv override is missing
    Given PYQA_PYTHON points to "artifacts/fake_py_outside.py"
    And PYQA_UV points to "/does/not/exist"
    When I run the "lint" wrapper with "--help"
    Then the wrapper exits with status 1
    And the wrapper reports a missing uv tool
