#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

TEST_PROMPT="$(realpath $(dirname ${BASH_SOURCE[0]})/pyqa-lint/ref_docs/PYTEST_GUIDELINES.md)"
if [[ ! -f "${TEST_PROMPT}" ]]; then
	echo "cannot find test prompt: ${TEST_PROMPT}"
	exit -1
fi

FIX=""
TESTCMD="uv run pytest --no-cov -q -q"

${TESTCMD}

if [[ $? != 0 ]]; then
	echo "test suite failed, fixing with claude"
	FIX="Examine the current directory and fix all the failing tests.  Make all tests selected by default and skip no tests."
else
	if [[ "$1" == "--enhance" ]]; then
		shift
		echo "test suite passed, enhancing test suite anyways..."
		FIX="Enhance the current test suite by increasing coverage, refactoring test suite code to improve robustness and reduce code duplication and work on increasing the comprehensiveness of existing tests."
	else
		echo "test suite passed, continuing..."
		exit 0
	fi
fi

if [[ "$1" != "" ]]; then
	FIX+=" $1"
fi

echo "Using: ${TEST_PROMPT} as basis."
echo "Using additional prompt: ${FIX}"

cat ${TEST_PROMPT} | uv run claude -p "Read the preceding to understand your identity and your goals.  ${FIX}" --model claude-opus-4-20250514 --verbose --dangerously-skip-permissions --allowedTools "Bash,Write,Edit,WebFetchTool,BatchTool,GrepTool" --output-format stream-json | tee .claude_test.json

${TESTCMD}
exit $?
