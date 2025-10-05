<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# Contributing to PyQA

Thanks for your interest in contributing! PyQA is an open source lint orchestration toolkit maintained by Blackcat Informatics® Inc. We welcome improvements to code, docs, automation, and tooling configuration.

## Code of Conduct

Please review the [Code of Conduct](CODE_OF_CONDUCT.md). We expect courteous, professional collaboration. To report unacceptable behaviour, email <conduct@blackcat.ca>.

## How Can I Contribute?

### Reporting Bugs

Before filing an issue, search [existing reports](https://github.com/paudley/py_qa/issues). Include:

* **Use a clear and descriptive title**
* **Describe the exact steps to reproduce the problem**
* **Provide specific examples to demonstrate the steps**
* **Describe the behavior you observed and what you expected**
* **Include logs and error messages**
* **Include your environment details** (OS, Docker version, core\_data commit)

### Suggesting Enhancements

Enhancement ideas are also tracked via [issues](https://github.com/paudley/py_qa/issues). When proposing a feature:

* **Use a clear and descriptive title**
* **Provide a detailed description of the suggested enhancement**
* **Provide specific examples to demonstrate the use case**
* **Describe the current behavior and explain the expected behavior**
* **Explain why this enhancement would be useful**

### Pull Requests

1. Fork the repo and create a feature branch off `main`
2. Follow the setup instructions in the README (`uv sync --group dev` etc.)
3. Make your changes adhering to the style guidelines and Code of Conduct
4. Add or update tests where relevant
5. Run `uv run pytest` (or the focused test suite relevant to your change)
6. Regenerate `ref_docs/tool-schema.json` when tool settings change (`uv run pyqa config export-tools ref_docs/tool-schema.json`)
7. Update docs if behaviour changes
8. Submit your pull request with a clear description and references to issues when applicable

## Development Setup

### Prerequisites

* Git
* Docker

### Setting Up Your Development Environment

```bash
# Clone your fork
git clone https://github.com/<your-username>/py_qa.git
cd py_qa
uv sync --group dev
```

## Documentation

* Update README.md if you change functionality
* Update inline documentation and docstrings
* Update catalog docs (`tooling/schema/SCHEMA.md`, `tooling/TOOLING.md`,
  `tooling/catalog/strategies/STRATEGIES.md`, `tooling/catalog/languages/LANGUAGES.md`,
  `tooling/catalog/_shared/SHARED.md`) when modifying catalog structure,
  strategies, or shared fragments

## Verification Checklist

Before requesting review, make sure you:

* \[ ] ran `uv run pytest` (or the subset relevant to your change)
* \[ ] regenerated `ref_docs/tool-schema.json` if tool settings changed
* \[ ] updated README.md or other docs (including catalog docs) if workflow/behaviour changed
* \[ ] confirmed CI checks (`uv run pyqa check-quality`) pass locally when possible

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

* `feat:` New feature
* `fix:` Bug fix
* `docs:` Documentation only changes
* `style:` Code style changes (formatting, etc.)
* `refactor:` Code change that neither fixes a bug nor adds a feature
* `perf:` Performance improvement
* `test:` Adding or updating tests
* `chore:` Changes to build process or auxiliary tools

Examples:

```
feat: add support for GitLab repositories
fix: handle empty commit messages gracefully
docs: update installation instructions for Windows
test: add integration tests for weekly summaries
```

## Questions?

Open an issue with the "question" label or start a GitHub discussion if you need help. For private matters, email <oss@blackcat.ca>.

## License

By contributing, you agree that your contributions will be licensed under the MIT License (SPDX: MIT).

## Acknowledgments

Thank you to everyone making PyQA better!
