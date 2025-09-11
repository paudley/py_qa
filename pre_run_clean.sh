#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
source $(dirname ${BASH_SOURCE[0]})/_check_repo.sh

declare -a REMOVE TREES
REMOVE=(
		"*.log"
		".*cache"
		".claude*.json"
		".coverage"
		".hypothesis"
		".stream*.json"
		".venv"
		"__pycache__"
		"chroma*db"
		"coverage*"
		"dist"
		"filesystem_store"
		"htmlcov*"
)
TREES=("examples" "packages")

declare -a REMOVE_find
REMOVE_find=()
for remove in ${REMOVE[@]}; do
		if [[ ${#REMOVE_find[@]} == 0 ]]; then
				REMOVE_find+=("-iname ${remove}")
		else
				REMOVE_find+=("-o -iname ${remove}")
		fi
done

#set -x
echo "cleaning TLD..."
find -maxdepth 1 \( ${REMOVE_find[@]} \) -print0 | xargs -0r rm -rf
for tree in ${TREES[@]}; do
		echo "cleaning ${tree}..."
		find ${tree} \( ${REMOVE_find[@]} \) -print0 | xargs -0r rm -rf
done
