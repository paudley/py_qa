#!/bin/bash
# SPDX-License-Identifier: MIT

source $(dirname ${BASH_SOURCE[0]})/_check_repo.sh
source $(dirname ${BASH_SOURCE[0]})/_check_venv.sh

AL=".aider-list.cmd"

echo "/reset" > ${AL}
echo "/read pyproject.toml README.md PLAN.md docs" >> ${AL}
echo "/read ref_docs/*.md" >> ${AL}


for fn in $( git ls-files "*.md" | egrep packages ); do
		echo "/read ${fn}" >> ${AL}
done

echo "/read src/spectra_schema/schema_definitions" >> ${AL}

echo "/drop LICENSE.md" >> ${AL}
echo "/drop uv.lock" >> ${AL}
echo "/drop __pycache__" >> ${AL}
echo "/drop .venv" >> ${AL}
echo "/drop snapshots" >> ${AL}
echo "/drop cassettes" >> ${AL}

echo "/add src/*/*.py" >> ${AL}
echo "/add src/*/*/*.py" >> ${AL}
echo "/add src/*/*/*/*.py" >> ${AL}
echo "/add src/*/*/*/*/*.py" >> ${AL}

echo "/read src/*/*.md" >> ${AL}
echo "/read src/*/*/*.md" >> ${AL}
echo "/read src/*/*/*/*.md" >> ${AL}
echo "/read src/*/*/*/*/*.md" >> ${AL}

echo "/drop __pycache__" >> ${AL}

echo "/add tests" >> ${AL}

echo "/model" >> ${AL}
