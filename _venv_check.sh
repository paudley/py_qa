#!/bin/bash
# source this snippet from other scripts to check that the venvs have been created correctly.

declare -a DIRS
DIRS=(".")
CWD=$(pwd)
for dir in "${DIRS[@]}"; do
		cd "${CWD}/${dir}" || exit 1
		if [[ ! -d ".venv" ]]; then
				uv venv
				uv sync --all-extras --locked --link-mode=hardlink --compile-bytecode
		fi
		if [[ ! -f ".venv/bin/activate" ]]; then
				echo "Failed to find a working venv in ${dir}"
				exit 1
		fi
done
cd "${CWD}" || exit 1
