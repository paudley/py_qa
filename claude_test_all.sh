#!/bin/bash
# SPDX-License-Identifier: MIT
source $(dirname ${BASH_SOURCE[0]})/_check_repo.sh
source $(dirname ${BASH_SOURCE[0]})/_check_venv.sh

CDW=$(pwd)

declare -a TESTDIRS
TESTDIRS=("packages/data-oracle" "examples/dataset-server-sample")

CONTINUE=1
while [[ ${CONTINUE} == 1 ]]; do
		CONTINUE=0
		for tdir in ${TESTDIRS[@]}; do
				echo "Running tests in ${tdir}..."
				cd "${CWD}/${tdir}"
				${CWD}/scripts/claude_test.sh
				if [[ $? != 0 ]]; then
					 CONTINUE=1
				fi
				cd "${CWD}"
		done

		if [[ ${CONTINUE} == 0 ]]; then
				for tdir in ${TESTDIRS[@]}; do
						echo "Enhancing tests in ${tdir}..."
						cd "${CWD}/${tdir}"
						${CWD}/scripts/claude_test.sh --enhance
						cd "${CWD}"
				done
		fi

done
