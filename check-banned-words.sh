#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

# Check commit messages for banned words/phrases
# Usage: check-banned-words.sh <commit_messages_file>

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Check if commit messages file was provided
if [ $# -ne 1 ]; then
    echo -e "${RED}❌ Error: Missing commit messages file argument${NC}"
    echo "Usage: $0 <commit_messages_file>"
    exit 1
fi

COMMIT_MESSAGES_FILE="$1"

# Check if the file exists
if [ ! -f "$COMMIT_MESSAGES_FILE" ]; then
    echo -e "${RED}❌ Error: Commit messages file not found: $COMMIT_MESSAGES_FILE${NC}"
    exit 1
fi

# Temporary file to collect all banned words
TEMP_BANNED_WORDS=$(mktemp)
trap 'rm -f "$TEMP_BANNED_WORDS"' EXIT

# Function to add banned words from a file
add_banned_words() {
    local file="$1"
    if [ -f "$file" ]; then
        # Skip empty lines and comments (lines starting with #)
        grep -v '^#' "$file" 2>/dev/null | grep -v '^[[:space:]]*$' >> "$TEMP_BANNED_WORDS" || true
    fi
}

# Add user's personal banned words file (highest priority, checked first)
USER_BANNED_WORDS="${HOME}/.banned-words"
add_banned_words "$USER_BANNED_WORDS"

# Add project-specific banned words file (medium priority)
PROJECT_BANNED_WORDS="${REPO_ROOT}/.banned-words"
add_banned_words "$PROJECT_BANNED_WORDS"

# Add internal list of banned words (lowest priority, always present)
# These are common problematic terms that should not appear in professional commits
cat >> "$TEMP_BANNED_WORDS" << 'EOF'
password123
secret_key
api_key_here
TODO: remove before commit
FIXME: security
hardcoded password
temp password
dummy password
fuck
shit
damn
quick hack
don't know why this works
no idea
cargo cult
spaghetti code
brain dead
stupid fix
skip ci
skip tests
disable tests
commented out tests
dumb
retarded
idiotic
moronic
copied from stackoverflow
stolen from
console.log
print debugging
binding.pry
pdb.set_trace()
EOF

# Sort and remove duplicates
sort -u "$TEMP_BANNED_WORDS" -o "$TEMP_BANNED_WORDS"

# Check for banned words in commit messages
FOUND_BANNED=false
BANNED_MATCHES=""

while IFS= read -r banned_word; do
    # Skip empty lines
    [ -z "$banned_word" ] && continue

    # Note: Using fixed string matching (-F) so no need to escape regex characters

    # Case-insensitive search for the banned word/phrase
    if grep -qiF -- "$banned_word" "$COMMIT_MESSAGES_FILE"; then
        FOUND_BANNED=true
        # Get the matching lines for context (use -F for fixed string)
        MATCHES=$(grep -niF -- "$banned_word" "$COMMIT_MESSAGES_FILE" | head -5)
        BANNED_MATCHES="${BANNED_MATCHES}\n  🚫 Found banned term: '${banned_word}'\n${MATCHES}\n"
    fi
done < "$TEMP_BANNED_WORDS"

# Report results
if [ "$FOUND_BANNED" = true ]; then
    echo -e "${RED}❌ Banned words/phrases detected in commit messages!${NC}"
    echo -e "${BANNED_MATCHES}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}Commit/push aborted due to banned content.${NC}"
    echo -e "${YELLOW}To configure banned words:${NC}"
    echo -e "  • Repository-wide: Edit ${PROJECT_BANNED_WORDS}"
    echo -e "  • Personal: Create/edit ${USER_BANNED_WORDS}"
    exit 1
else
    echo -e "${GREEN}✅ No banned words found in commit messages${NC}"
    exit 0
fi
