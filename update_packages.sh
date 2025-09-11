#!/bin/bash

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")"/_check_repo.sh

if [[ -f "scripts/lint.sh" ]]; then
		./scripts/lint.sh --install
fi

find . -name 'pyproject.toml' -type f -print | egrep -v pyreadstat | egrep -v '.venv'| while read -r projfile; do
		PROJECT_DIR=$(dirname "${projfile}")
		if [[ ! -d ${PROJECT_DIR} ]]; then
				continue
		fi
		cd "${PROJECT_DIR}" || exit
		echo "updating packages in ${PROJECT_DIR}"
		if [[ ! -d .venv ]]; then
				uv venv
		fi
		uv sync -U --all-extras --all-groups --managed-python --link-mode=hardlink --compile-bytecode
done
