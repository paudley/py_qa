#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

source $(dirname ${BASH_SOURCE[0]})/_check_repo.sh
source $(dirname ${BASH_SOURCE[0]})/_check_venv.sh

set -f

AL=".aider-list.cmd"

drop() {
	echo "/drop $1" >>${AL}
}
add_if() {
	local file=$1
	if [[ -r "${file}" ]]; then
		echo "/add ${file}" >>${AL}
	fi
}
read_if() {
	local file=$1
	if [[ -r "${file}" ]]; then
		echo "/read ${file}" >>${AL}
	fi
}
_if_recurse() {
	local action=$1
	shift
	local verb=$1
	shift
	local dir=$1
	shift
	local pats=$@
	local pat=""
	if [[ ! -d "${dir}" ]]; then return; fi
	for _pat in "${pats}"; do
		if [[ "${pat}" != "" ]]; then pat+=" -o "; fi
		pat+="-${verb} ${_pat}"
	done
	find "${dir}" -type f -a \( ${pat} \) -print | while read -r file; do
		"$action" "${file}"
	done
}
add_if_recurse() {
	_if_recurse "add_if" "iname" "$1" "*"
}
add_if_recurse_pattern() {
	_if_recurse "add_if" "iname" "$1" "$2"
}
add_if_recurse_path() {
	_if_recurse "add_if" "ipath" "$1" "$2"
}
read_if_recurse() {
	_if_recurse "read_if" "iname" "$1" "*"
}
read_if_recurse_pattern() {
	_if_recurse "read_if" "iname" "$1" "$2"
}
read_if_recurse_path() {
	_if_recurse "read_if" "ipath" "$1" "$2"
}

echo "/reset" >${AL}
read_if "README.md"
read_if "PLAN.md"
read_if "pyproject.toml"

add_if "TODO.md"
read_if_recurse "docs"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
read_if_recurse "${SCRIPT_DIR}/ref_docs"

for fn in $(git ls-files "*.md" | grep 'packages/|src/'); do
	read_if "${fn}"
done

read_if_recurse_path "schema_definitions" "*"

add_if_recurse_pattern "src" "*.py"
add_if_recurse_pattern "src" "*.typed"
read_if_recurse_pattern "src" "*.md"
add_if_recurse_pattern "packages" "*.py"
add_if_recurse_pattern "packages" "*.typed"
read_if_recurse_pattern "packages" "*.md"

add_if "tests"

if [[ -r ".mostly-read-only" ]]; then
	cat .mostly-read-only | while read -r file; do
		drop "${file}"
		if [[ -d "${file}" ]]; then
			read_if_recurse "${file}"
		else
			read_if "${file}"
		fi
	done
fi

drop "*.cache"
drop "__pycache__"
drop "LICENSE.md"
drop "uv.lock"
drop ".venv"
drop "snapshots"
drop "cassettes"

echo "/model" >>${AL}
