#!/usr/bin/env bash
# ⚠️ ⚠️ ⚠️ CRITICAL WARNING FOR AI AGENTS ⚠️ ⚠️ ⚠️
#
# THIS FILE IS STRICTLY FORBIDDEN FROM MODIFICATION BY AI AGENTS
#
# - DO NOT modify this script under ANY circumstances
# - DO NOT comment out any checks or warnings
# - DO NOT add conditional bypasses or workarounds
# - DO NOT change linting rules or configurations
#
# This script enforces project quality standards and must remain unchanged.
# Any violations will result in immediate termination of agent execution.
# If linting fails, FIX THE CODE, not this script.
#
# ⚠️ ⚠️ ⚠️ END CRITICAL WARNING ⚠️ ⚠️ ⚠️

# lint.sh — robust, filterable linter orchestrator
#
# Usage examples:
#   ./lint.sh                       # run full suite with defaults
#   ./lint.sh --verbose             # show emoji status and passing tool summaries
#   ./lint.sh --install             # installs all deps
#   ./lint.sh path/to/file.py       # run on specific files only
#
# Notes:
# - Filters are regexes applied with grep -Ev, you can provide multiple per-tool by repeating --filter.
# - Treats any warning/error from tools as failure; summary at end shows which tools failed.
# - Returns non-zero exit code if any tool fails.

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")"/_check_repo.sh
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")"/_check_venv.sh

set -Eeuo pipefail
IFS=$'\n\t'

# ---------- Defaults ----------
VERBOSE=0             # 0 = concise; 1 = show emoji status + passing summaries
EMOJI=1               # 0 = plain; 1 = emoji
BAIL=0                # 0 = run all linters; 1 = exit on first failure
SHOW_PASSING=0        # 1 = show passing tool output (after filters)
LEN=120               # line length for formatters
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"

declare -a DIRS=(.)
declare -a EXCLUDE=(.venv .git build dist .mypy_cache .ruff_cache .pytest_cache .tox .eggs pyreadstat pyreadstat_patch)
declare -a FILES=()                   # explicit files passed via CLI
declare -a FILES_FILTERED=()          # files but without some things like tests.

# Per-tool filters (grep -Ev). Use ';;' to separate multiple patterns internally.
# Users can add to these via repeated --filter TOOL:'regex'
declare -A FILTERS=(
		[bandit]='^Run started:.*$|^Test results:$|^No issues identified\.$|^Files skipped \(.*\):$'
		[black]='^All done! [0-9]+ files? (re)?formatted\.$|^All done! ✨ .* files? left unchanged\.$'
		[isort]='^SUCCESS: .* files? are correctly sorted and formatted\.$|^Nothing to do\.$'
		[mypy]='^Success:.*'
		[pylint]='^Your code has been rated at 10\.00/10.*$|^----|^Your code has been rated|^$|^\*\*\*'
		[pyright]='^No configuration file found\..*|^No pyright configuration found\..*|^0 errors, 0 warnings, 0 informations$|^Found 0 errors in .* files? \(.*\)$'
		[pytest]='^=+ .* in .*s =+$|^collected \[0-9]+ items$|^platform .* - Python .*|^cache cleared$'
		[ruff]='^Found 0 errors\..*$|^All checks passed!$|^.* 0 files? reformatted.*$'
		[vulture]='^No dead code found$'
)


# Linter arguments.
declare -a OPTS_RUFF=("--respect-gitignore" "--ignore" "F401" "--output-format=concise" "--line-length=${LEN}"
											"--target-version=py313")
declare -a OPTS_ISORT=("--profile" "google" "--py" "313" "--virtual-env" ".venv" "--remove-redundant-aliases" "--ac"
											 "--srx" "--gitignore" "--ca" "--cs" "-e" "-q" "-l" "${LEN}")
declare -a OPTS_BANDIT=("-q" "-ll" "-c" "pyproject.toml")
declare -a OPTS_VULTURE=("--min-confidence=80")
declare -a OPTS_MYPY=("--exclude-gitignore" "--sqlite-cache" "--strict" "--warn-redundant-casts" "--warn-unused-ignores"
											"--no-implicit-reexport" "--show-error-codes" "--show-column-numbers" "--warn-unreachable"
											"--disallow-untyped-decorators" "--disallow-any-generics" "--check-untyped-defs")
declare -a OPTS_PYLINT=("--fail-on=W" "--jobs=${JOBS}" "--output-format=parseable" "--enable-all-extensions"
												"--bad-functions=print" "--max-line-length=${LEN}" "--max-complexity=10" "--min-similarity-lines=10"
												"--ignore-long-lines='^\\s*(# )?<?https?://\\S+>?$'"
												"--disable=too-many-try-statements,no-else-return,suppressed-message,locally-disabled,empty-comment,no-self-use,protected-access,too-few-public-methods,consider-alternative-union-syntax,line-too-long"
												"--fail-under=9.5")
declare -a OPTS_PYTEST=("--no-cov" "-p" "no:allure_pytest" "-p" "no:allure_pytest_bdd")
declare -a OPTS_PYUPGRADE=("--py313-plus")

# ---------- UI helpers ----------
_color() { # $1=color code, $2=message
		local c="$1"; shift || true
		printf "\033[%sm%s\033[0m" "$c" "$*"
}
emoji() {
		(( EMOJI )) || { printf "%s" "$2"; return; }
		printf "%s" "$1"
}
info()   { printf "%s\n" "$(emoji "ℹ️ " "")$*"; }
ok()     { printf "%s\n" "$(emoji "✅ " "")$*"; }
warn()   { printf "%s\n" "$(emoji "⚠️ " "")$*"; }
fail()   { printf "%s\n" "$(emoji "❌ " "")$*"; }

section() {
		local title="$1"
		if (( VERBOSE )); then
				printf "\n%s %s %s\n" "$(_color '1;34' '───')" "$(_color '1;36' "$title")" "$(_color '1;34' '───')"
		fi
}

error_exit() {
		echo "❌ FAILED running linters. You are not ready to commit."
		echo "  Treat all warnings as errors regardless of what you think their severity or importance is."
    echo "   - all lint warnings are CRITICAL in this project."
		echo "   - commits with ANY lint warnings will be denied automatically."
		echo "   - it is always possible to write lint free versions of code."
		exit 1
}

usage() {
		cat <<'USAGE'
Usage: ./lint.sh [options] [FILES... or DIRS...]
Options:
	-v, --verbose              Show emoji status + passing tool output (after filtering)
	-q, --quiet                Minimal output (overrides verbose)
			--no-emoji             Disable emoji in output
			--install              Install all needed dependancies
      --bail                 Error out after the first failing linter
			--show-passing         Show passing tool output (after filters)
			--dir PATH             Add directory to scan (default: .) (repeatable)
			--exclude PATH         Add directory/file to exclude from file discovery (repeatable)
	-h, --help                 Show this help

Examples:
	./lint.sh --verbose
	./lint.sh my_project/
USAGE
}

PIPPKGS=$(uv pip list | awk '{print $1}')

function uv_dev_maybe_add_also {
		if grep -s -i "$1" <<< "${PIPPKGS}" > /dev/null 2>&1; then
				uv add -q --dev "$2"
		fi
}

declare -a UV_REQUIRED_DEPS=(
		"autopep8"
		"bandit[baseline,toml,sarif]"
		"black"
		"bs4"
		"isort"
		"markdown"
		"mypy-extensions"
		"mypy"
		"pycodestyle"
		"pyflakes"
		"pylint-htmf"
		"pylint-plugin-utils"
		"pylint-pydantic"
		"pylint"
		"pyright"
		"pyupgrade"
		"ruff"
		"twine"
		"types-aiofiles"
		"types-markdown"
		"types-regex"
		"types-decorator"
		"types-pexpect"
		"typing-extensions"
		"typing-inspection"
		"uv"
		"vulture"
)

function uv_dev_maybe_stubgen {
		local pkg="$1"
		shift
		if grep -s -i "${pkg}" <<< "${PIPPKGS}" > /dev/null 2>&1; then
				if [[ ! -d "stubs" ]]; then mkdir stubs; fi
				if [[ ! -d "stubs/$1" ]]; then
						info "generated mypy stubs for ${pkg}..."
						for pkgs in "$@"; do
								uv run stubgen --package "${pkgs}" --output "stubs/${pkgs}" 2>&1
						done
				fi
		fi
}


function install_deps {
		info "installing lint.sh dev dependancies..."
		uv add -q --dev "${UV_REQUIRED_DEPS[@]}"
		uv_dev_maybe_add_also PyMySQL types-PyMySQL
		uv_dev_maybe_add_also cachetools types-cachetools
		uv_dev_maybe_add_also cffi types-cffi
		uv_dev_maybe_add_also colorama types-colorama
		uv_dev_maybe_add_also dateutil types-python-dateutil
		uv_dev_maybe_add_also defusedxml types-defusedxml
		uv_dev_maybe_add_also docutils types-docutils
		uv_dev_maybe_add_also gevent types-gevent
		uv_dev_maybe_add_also greenlet types-greenlet
		uv_dev_maybe_add_also html5lib types-html5lib
		uv_dev_maybe_add_also httplib2 types-httplib2
		uv_dev_maybe_add_also json types-ujson
		uv_dev_maybe_add_also jsonschema types-jsonschema
		uv_dev_maybe_add_also libsass types-libsass
		uv_dev_maybe_add_also networkx types-networkx
		uv_dev_maybe_add_also openpyxl types-openpyxl
		uv_dev_maybe_add_also pandas pandas-stubs
		uv_dev_maybe_add_also protobuf types-protobuf
		uv_dev_maybe_add_also psutil types-psutil
		uv_dev_maybe_add_also psycopg2 types-psycopg2
		uv_dev_maybe_add_also pyasn1 types-pyasn1
		uv_dev_maybe_add_also pyarrow pyarrow-stubs
		uv_dev_maybe_add_also pycurl types-pycurl
		uv_dev_maybe_add_also pygments types-pygments
		uv_dev_maybe_add_also pyopenssl types-pyopenssl
		uv_dev_maybe_add_also pytz types-pytz
		uv_dev_maybe_add_also pywin32 types-pywin32
		uv_dev_maybe_add_also pyyaml types-pyyaml
		uv_dev_maybe_add_also requests types-requests
		uv_dev_maybe_add_also scipy scipy-stubs
		uv_dev_maybe_add_also setuptools types-setuptools
		uv_dev_maybe_add_also shapely types-shapely
		uv_dev_maybe_add_also simplejson types-simplejson
		uv_dev_maybe_add_also tabulate types-tabulate
		uv_dev_maybe_add_also tensorflow types-tensorflow
		uv_dev_maybe_add_also tqdm types-tqdm
		uv_dev_maybe_stubgen chromadb chromadb
		uv_dev_maybe_stubgen geopandas geopandas
		uv_dev_maybe_stubgen polars polars
		uv_dev_maybe_stubgen pyarrow pyarrow
		uv_dev_maybe_stubgen pyarrow pyarrow.parquet
		uv_dev_maybe_stubgen pyreadstat pyreadstat
		uv_dev_maybe_stubgen scikit-learn sklearn
		uv_dev_maybe_stubgen tolerantjson tolerantjson
		info "done."
		exit 0
}

declare -a PYLINT_PLUGINS
PYLINT_PLUGINS=(
		"pylint.extensions.bad_builtin"
		"pylint.extensions.broad_try_clause"
		"pylint.extensions.check_elif"
		"pylint.extensions.code_style"
		"pylint.extensions.comparison_placement"
		"pylint.extensions.confusing_elif"
		"pylint.extensions.consider_ternary_expression"
		"pylint.extensions.dict_init_mutate"
		"pylint.extensions.docparams"
		"pylint.extensions.docstyle"
		"pylint.extensions.empty_comment"
		"pylint.extensions.eq_without_hash"
		"pylint.extensions.for_any_all"
		"pylint.extensions.magic_value"
		"pylint.extensions.mccabe"
		"pylint.extensions.overlapping_exceptions"
		"pylint.extensions.redefined_loop_name"
		"pylint.extensions.redefined_variable_type"
		"pylint.extensions.set_membership"
		"pylint.extensions.typing"
		"pylint.extensions.while_used"
		"pylint_htmf"
		#		"pylint_ml"
		"pylint_pydantic"
		#		"pylint_pytest"
)
declare PYLINT_plugopt=""
for plug in "${PYLINT_PLUGINS[@]}"; do
		if [[ ${PYLINT_plugopt} == "" ]]; then
				PYLINT_plugopt="--load-plugins=${plug}"
		else
				PYLINT_plugopt+=",${plug}"
		fi
done

# ---------- CLI parsing ----------
while (($#)); do
		case "$1" in
				-v|--verbose) VERBOSE=1; SHOW_PASSING=1; shift ;;
				-q|--quiet)   VERBOSE=0; SHOW_PASSING=0; shift ;;
				--no-emoji)   EMOJI=0; shift ;;
				--bail)       BAIL=1; shift ;;
				--show-passing) SHOW_PASSING=1; shift ;;
				--install)    install_deps ;;
				--dir)
						DIRS+=("${2:?}"); shift 2 ;;
				--exclude)
						EXCLUDE+=("${2:?}"); shift 2 ;;
				-h|--help) usage; exit 0 ;;
				--) shift; break ;;
				-*)
						fail "Unknown option: $1"
						usage
						exit 2 ;;
				*)
						FILES+=("$1"); shift ;;
		esac
done

# Also accept trailing FILES after '--'
if (($#)); then
		FILES+=("$@")
fi

# ---------- Env / tool helpers ----------
have() { command -v "$1" >/dev/null 2>&1; }

USE_UV=0
if have uv && [[ -f pyproject.toml ]]; then
		USE_UV=1
fi
if [[ $USE_UV == 0 ]]; then
		fail "uv is required to run this script."
		exit 1
fi

run_env() {
		# run inside uv isolation if available
		if (( USE_UV )); then
				uv run --quiet --all-extras --group dev --isolated --locked "$@"
		else
				"$@"
		fi
}

ensure_files_list() {
		# If user provides specific files or directories, use them. Otherwise, use DIRS.
		local search_targets=("${FILES[@]}")
		if ((${#search_targets[@]} == 0)); then
				search_targets=("${DIRS[@]}")
		fi

		# Expand directories into file lists and collect all files
		local collected_files=()
		# Use git ls-files for the default case (running in repo root with no args)
		if ((${#FILES[@]} == 0)) && ((${#DIRS[@]} == 1)) && [[ "${DIRS[0]}" == "." ]]; then
				if ! have git; then
						warn "Missing GIT. You probably do not have a working environment."
						exit 1
				fi
				# Find all files tracked by git to support various linters
				mapfile -t collected_files < <(git ls-files 2>/dev/null || true)
		else
				for target in "${search_targets[@]}"; do
						if [[ -d "$target" ]]; then
								# It's a directory, find all files within it, excluding dotfiles/dirs.
								mapfile -t -O "${#collected_files[@]}" collected_files < <(find "$target" -type f -not -path '*/.*')
						elif [[ -f "$target" ]]; then
								# It's a file, add it directly.
								collected_files+=("$target")
						fi
				done
		fi

		# Overwrite global FILES with the unique, sorted list of collected files.
		if ((${#collected_files[@]} > 0)); then
				mapfile -t FILES < <(printf "%s\n" "${collected_files[@]}" | sort -u)
		else
				FILES=()
		fi

		# Apply excludes (simple prefix match)
		if ((${#EXCLUDE[@]})); then
				local -a kept=()
				local f e skip
				for f in "${FILES[@]}"; do
						skip=0
						if [[ ! -f "$f" ]]; then
								skip=1
						else
								for e in "${EXCLUDE[@]}"; do
										[[ "$f" == "$e"* || "$f" == "./$e"* ]] && { skip=1; break; }
								done
						fi
						(( ! skip )) && kept+=("$f")
				done
				FILES=("${kept[@]}")
		fi

		# Generate the filtered file list.
		FILES_FILTERED=()
		for f in "${FILES[@]}"; do
				if [[ ! "$f" =~ tests ]]; then
						FILES_FILTERED+=("$f")
				fi
		done
}

# Create the exclude options
declare -a EXCLUDE_opt=()
for d in "${EXCLUDE[@]}"; do
		EXCLUDE_opt+=("--exclude")
		EXCLUDE_opt+=("${d}")
done

# ---------- Filtering ----------
apply_filters() { # $1=tool $2=tmpfile
		local tool="$1" tmp="$2" out rx
		if [[ -z "${FILTERS[$tool]:-}" ]]; then
				cat "$tmp"
				return 0
		fi
		out="$(cat "$tmp" || true)"
		IFS=';;' read -r -a pats <<< "${FILTERS[$tool]}"
		for rx in "${pats[@]}"; do
				# grep -Ev returns non-zero if all lines are filtered; ignore that with '|| true'
				out="$(printf "%s" "$out" | grep -Ev -- "$rx" || true)"
		done
		printf "%s" "$out"
}

# ---------- Tool runners ----------
declare -a FAILED_TOOLS=()
declare -i TOTAL_FAILS=0

run_tool() { # $1=fail_ok, $2=extensions, $3=name, $4=file_list_name, $5=-- args...
		local fail_ok="$1"; shift
		local extensions="$1"; shift
		local name="$1"; shift
		local file_list_name="$1"; shift
		shift # for --

		local -a name_parts
		read -ra name_parts <<< "$name"
		local -a cmd=("${name_parts[@]}" "$@")
		local -a files_to_process=()

		if [[ -n "$file_list_name" ]]; then
				local -n files_ref="$file_list_name" # nameref to the global array

				if [[ -z "$extensions" ]]; then
						files_to_process=("${files_ref[@]}")
				else
						IFS=',' read -ra ext_array <<< "$extensions"
						for f in "${files_ref[@]}"; do
								for ext in "${ext_array[@]}"; do
										# Ensure we match the end of the string for the extension
										if [[ "$f" == *"$ext" ]]; then
												files_to_process+=("$f")
												break
										fi
								done
						done
				fi

				if ((${#files_to_process[@]} == 0)); then
						(( VERBOSE )) && info "▶ Skipping ${name} (no relevant files to check)"
						return 0
				fi
				cmd+=("${files_to_process[@]}")
		fi

		local tmp
		tmp="$(mktemp)"
		local header
		header="$name"
		(( VERBOSE )) && info "▶ Running ${header}…"

		set +e
		run_env "${cmd[@]}" >"$tmp" 2>&1
		local rc=$?
		set -e

		local filtered
		filtered="$(apply_filters "$name" "$tmp")"

		if (( rc == 0 )); then
				(( VERBOSE || SHOW_PASSING )) && { ok "${header} passed"; [[ -n "$filtered" ]] && printf "%s\n" "$filtered"; }
		else
				if [[ "$fail_ok" == "1" ]]; then
						warn "${header} failed but it's ok (exit $rc)"
				else
						fail "${header} failed (exit $rc)"
				fi
				[[ -n "$filtered" ]] && printf "%s\n" "$filtered"
				if [[ "$fail_ok" != "1" ]]; then
						FAILED_TOOLS+=("$name")
						(( TOTAL_FAILS++ )) || true
						if ((BAIL)); then
								error_exit
						fi
				fi
		fi
		rm -f "$tmp"
		set +e
		return $rc
}

# ---------- Prepare ----------
ensure_files_list

if (( USE_UV )); then
		# keep lock fresh; quick no-op if already up to date
		uv lock --quiet || true
fi

if [[ -x "scripts/gen_aider_list.sh" ]]; then
		scripts/gen_aider_list.sh
fi

# ---------- Execute ----------
section "Formatting"

# Initial black format pass, so that line numbers make sense in errors consistently.
run_tool 1 ".py" black FILES -- -l ${LEN} -q

# Initial ruff pass to auto-fix things, no reporting.
run_tool 1 ".py" ruff FILES -- check "${EXCLUDE_opt[@]}" "${OPTS_RUFF[@]}" --fix --no-unsafe-fixes --fix-only --silent

# No we report anything we could not auto-fix
run_tool 0 ".py" ruff FILES -- check "${EXCLUDE_opt[@]}" "${OPTS_RUFF[@]}" --fix --no-unsafe-fixes --no-show-fixes --quiet

# pyupgrade
run_tool 1 ".py" pyupgrade FILES -- "${OPTS_PYUPGRADE[@]}"

# Check the github workflows
if command -v actionlint >/dev/null 2>&1; then
		if compgen -G ".github/workflows/*.yml" > /dev/null; then
				run_tool 0 "" actionlint "" -- .github/workflows/*.yml
		else
				info "skipping actionlint, no workflows found."
		fi
else
		warn "skipping actionlint, binary not found."
fi

# Second black format pass, so that line numbers make sense in errors consistently.
run_tool 0 ".py" black FILES -- -l ${LEN} -q

# Sort the imports.
run_tool 0 ".py" isort FILES -- "${OPTS_ISORT[@]}"

section "Type checking"

# Pyright
run_tool 0 ".py" pyright FILES_FILTERED --

# Mypy in semi-strict mode.
run_tool 0 ".py" mypy FILES_FILTERED -- "${EXCLUDE_opt[@]}" "${OPTS_MYPY[@]}"

section "Linting"

# pylint for the rest.
run_tool 0 ".py" pylint FILES -- "${OPTS_PYLINT[@]}" "${PYLINT_plugopt}"

# Bandit for security scanning.
run_tool 0 ".py" bandit FILES -- "${OPTS_BANDIT[@]}"

# Vulture for dead code identification.
run_tool 0 ".py" vulture FILES -- "${OPTS_VULTURE[@]}"

section "Tests"

# Run pytest, capturing output and only showing it on failure.
if grep -s "smoke" tests/conftest.py pyproject.toml > /dev/null 2>&1; then
		run_tool 0 "" pytest "" -- "${OPTS_PYTEST[@]}" -m smoke -c /dev/null
else
		warn "skipping pytest, no smoke tests found."
fi

# ---------- Summary ----------
printf "\n"
if (( TOTAL_FAILS > 0 )); then
		error_exit
fi

ok "All lint checks passed!"
exit 0
