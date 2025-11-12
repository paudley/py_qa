<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Shared Knobs Across pyqa Tools

The table below summarises which bundled tools participate in the project-wide
shared settings introduced in `Config`:

| Setting Group                         | Tools                                                       | Notes                                                                                                                |
| ------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Line Length (`execution.line_length`) | black, isort, ruff, ruff-format, pylint, luacheck, prettier | Mapped to `--line-length`, `--max-line-length`, `--print-width`, and luacheck line limits.                           |
| Complexity (`[complexity]`)           | pylint, luacheck                                            | Controls `--max-complexity`, `--max-args`, `--max-positional-arguments`, and luacheck `--max-cyclomatic-complexity`. |
| Strictness (`[strictness]`)           | mypy, pyright, tsc                                          | Drives mypy strict bundle (`show-error-codes`, etc.) and TypeScript `--strict`; pyright honours the config layer.    |
| Severity (`[severity]`)               | bandit, pylint                                              | Sets Bandit `--severity-level` & `--confidence-level`, and pylint `--fail-under`.                                    |

To override per project, add the corresponding sections to `.pyqa_lint.toml` or
`pyproject.toml`:

```toml
[complexity]
max_complexity = 12
max_arguments = 6

[strictness]
type_checking = "standard"  # lenient | standard | strict
```

Individual tools can still be customised under `[tools.<name>]`; the shared
settings act as sensible defaults to keep multiple linters aligned.

## Sensitivity Presets

Use the global sensitivity knob to tune several related thresholds at once. The
values below are applied unless a CLI flag (e.g. `--line-length`) or explicit
config override is supplied.

| Sensitivity          | Line Length | Complexity (max / args) | Type Checking | Bandit (severity/confidence) | Pylint Fail-Under | Max Warnings (eslint/stylelint) |
| -------------------- | ----------- | ----------------------- | ------------- | ---------------------------- | ----------------- | ------------------------------- |
| `low`                | 140         | 15 / 7                  | lenient       | low / low                    | 8.0               | 200                             |
| `medium` *(default)* | 120         | 10 / 5                  | strict        | medium / medium              | 9.5               | cleared                         |
| `high`               | 110         | 8 / 4                   | strict        | high / high                  | 9.75              | 5                               |
| `maximum`            | 100         | 6 / 3                   | strict        | high / high                  | 9.9               | 0                               |

Switching profiles always re-applies the shared defaults above; direct CLI or
config entries continue to take precedence for fine-grained control.
