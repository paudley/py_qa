#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

source $(dirname ${BASH_SOURCE[0]})/_check_repo.sh
source $(dirname ${BASH_SOURCE[0]})/_check_venv.sh

AL=".aider-list.cmd"

echo "/reset" > ${AL}
echo "/read pyproject.toml README.md PLAN.md" >> ${AL}
echo "/add TODO.md" >> ${AL}
if [[ -d docs ]]; then
  echo "/read docs" >> ${AL}
fi
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
echo "/read ${SCRIPT_DIR}/ref_docs/*.md" >> ${AL}


for fn in $( git ls-files "*.md" | egrep packages ); do
		echo "/read ${fn}" >> ${AL}
done

echo "/read */*/schema_definitions" >> ${AL}

echo "/drop LICENSE.md" >> ${AL}
echo "/drop uv.lock" >> ${AL}
echo "/drop __pycache__" >> ${AL}
echo "/drop .venv" >> ${AL}
echo "/drop snapshots" >> ${AL}
echo "/drop cassettes" >> ${AL}

if [[ -d src ]]; then
  echo "/add src/*/*.py" >> ${AL}
  echo "/add src/*/*/*.py" >> ${AL}
  echo "/add src/*/*/*/*.py" >> ${AL}
  echo "/add src/*/*/*/*/*.py" >> ${AL}
  echo "/read src/*/*.md" >> ${AL}
  echo "/read src/*/*/*.md" >> ${AL}
  echo "/read src/*/*/*/*.md" >> ${AL}
  echo "/read src/*/*/*/*/*.md" >> ${AL}
fi

if [[ -d packages ]]; then
  echo "/add packages/*/src/*/*.py" >> ${AL}
  echo "/add packages/*/src/*/*/*.py" >> ${AL}
  echo "/add packages/*/src/*/*/*/*.py" >> ${AL}
  echo "/add packages/*/src/*/*/*/*/*.py" >> ${AL}
  echo "/read packages/*/src/*/*.md" >> ${AL}
  echo "/read packages/*/src/*/*/*.md" >> ${AL}
  echo "/read packages/*/src/*/*/*/*.md" >> ${AL}
  echo "/read packages/*/src/*/*/*/*/*.md" >> ${AL}
fi

echo "/drop __pycache__" >> ${AL}

echo "/add tests" >> ${AL}

echo "/model" >> ${AL}
