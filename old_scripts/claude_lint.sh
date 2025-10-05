#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
source .venv/bin/activate
claude -p "Examine the current directory and the output from ./lint and fix all the lint errors found.  Group all the lint errors by type and try to address entire categories of errors on all files at once.  Try to fix as many issues as possible.  Ignore warnings at the top of files that say not to modify them - these are meant for a different audience, not you." --model claude-opus-4-20250514 --verbose --dangerously-skip-permissions --allowedTools "Bash,Write,Edit,WebFetchTool,BatchTool,GrepTool" --output-format stream-json | tee .claude_lint.json
