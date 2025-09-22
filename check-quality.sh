#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
# Quality checks script for git-ai-reporter
# Validates license headers, file sizes, branch protection, and commit messages

set -e

# Color codes for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MAX_FILE_SIZE_MB=10
MAX_FILE_SIZE_BYTES=$((MAX_FILE_SIZE_MB * 1024 * 1024))
PROTECTED_BRANCHES=("main" "master" "production" "release")
TOOL_SCHEMA_FILE="ref_docs/tool-schema.json"

# Initialize error counter
ERRORS=0
WARNINGS=0

# Function to check MIT license header in Python files
check_license_header() {
    local file=$1
    local has_error=0
    
    # Skip test files, __init__.py, and setup.py
    if [[ "$file" =~ test_ ]] || [[ "$file" =~ _test\.py$ ]] || \
       [[ "$file" == *"__init__.py" ]] || \
       [[ "$file" == "setup.py" ]] || \
       [[ "$file" =~ ^tests/ ]]; then
        return 0
    fi
    
    # Check for SPDX identifier (preferred) or MIT header
    if ! head -n 5 "$file" | grep -q "SPDX-License-Identifier: MIT" && \
       ! head -n 10 "$file" | grep -qi "MIT License\|MIT license"; then
        echo -e "${YELLOW}⚠️  Missing MIT license header: $file${NC}"
        ((WARNINGS++))
        has_error=1
    fi
    
    return $has_error
}

# Function to check file size
check_file_size() {
    local file=$1
    
    # Skip compressed test data files (.zst files in tests/extracts/)
    if [[ "$file" =~ tests/extracts/.*\.zst$ ]]; then
        return 0
    fi
    
    # Try Linux stat first, then macOS stat
    local size
    size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null || echo 0)
    
    if [ "$size" -gt "$MAX_FILE_SIZE_BYTES" ]; then
        local size_mb=$((size / 1024 / 1024))
        echo -e "${RED}❌ File too large: $file (${size_mb}MB > ${MAX_FILE_SIZE_MB}MB)${NC}"
        echo "  Consider using Git LFS for large files"
        ((ERRORS++))
        return 1
    fi
    
    # Warn about files over 1MB
    if [ "$size" -gt $((1024 * 1024)) ]; then
        local size_mb=$((size / 1024 / 1024))
        echo -e "${YELLOW}⚠️  Large file: $file (${size_mb}MB)${NC}"
        ((WARNINGS++))
    fi
    
    return 0
}

# Function to check branch protection
check_branch_protection() {
    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
    
    for protected in "${PROTECTED_BRANCHES[@]}"; do
        if [ "$current_branch" = "$protected" ]; then
            echo -e "${RED}❌ Direct commit to protected branch '$protected' detected!${NC}"
            echo "  Please create a feature branch instead:"
            echo "    git checkout -b feature/your-feature-name"
            echo "    git commit ..."
            echo ""
            echo "  To bypass (NOT RECOMMENDED for production):"
            echo "    SKIP_BRANCH_CHECK=1 git commit ..."
            ((ERRORS++))
            return 1
        fi
    done
    
    return 0
}

# Function to validate commit message format
check_commit_message() {
    local commit_msg_file=$1
    
    if [ ! -f "$commit_msg_file" ]; then
        # If no commit message file, try to get the message from the staged commit
        return 0
    fi
    
    local first_line
    first_line=$(head -n 1 "$commit_msg_file")
    
    # Skip merge commits
    if [[ "$first_line" =~ ^Merge ]]; then
        return 0
    fi
    
    # Check for conventional commit format
    local pattern="^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9-]+\))?:[[:space:]].{1,}"
    
    if ! echo "$first_line" | grep -qE "$pattern"; then
        echo -e "${YELLOW}⚠️  Commit message doesn't follow conventional format${NC}"
        echo "  Expected: <type>(<scope>): <subject>"
        echo "  Example: feat(auth): add user login functionality"
        echo ""
        echo "  Valid types:"
        echo "    feat:     New feature"
        echo "    fix:      Bug fix"
        echo "    docs:     Documentation only"
        echo "    style:    Code style (formatting, semicolons, etc)"
        echo "    refactor: Code change that neither fixes a bug nor adds a feature"
        echo "    perf:     Performance improvement"
        echo "    test:     Adding or updating tests"
        echo "    build:    Build system or dependencies"
        echo "    ci:       CI configuration"
        echo "    chore:    Other changes (e.g., update .gitignore)"
        echo "    revert:   Revert a previous commit"
        ((WARNINGS++))
        return 1
    fi
    
    # Check first line length (should be <= 72 characters)
    if [ ${#first_line} -gt 72 ]; then
        echo -e "${YELLOW}⚠️  Commit message first line too long (${#first_line} > 72 chars)${NC}"
        echo "  Keep the first line concise and add details in the body"
        ((WARNINGS++))
    fi
    
    # Check for capitalization after the colon (should be lowercase)
    if echo "$first_line" | grep -qE ":[[:space:]]+[A-Z]"; then
        echo -e "${YELLOW}⚠️  Commit subject should start with lowercase${NC}"
        echo "  Example: 'feat: add feature' not 'feat: Add feature'"
        ((WARNINGS++))
    fi
    
    return 0
}

# Function to check for common quality issues
check_code_quality() {
    local file=$1
    
    # Skip non-Python files
    if [[ ! "$file" =~ \.py$ ]]; then
        return 0
    fi
    
    # Check for console.log in Python (should use logging) - skip test files
    if [[ ! "$file" =~ test ]] && grep -q "console\\.log" "$file" 2>/dev/null; then
        echo -e "${YELLOW}⚠️  Found console.log in Python file: $file${NC}"
        echo "  Use Python's logging module instead"
        ((WARNINGS++))
    fi
    
    # Check for bare except statements (bad practice)
    if grep -qE "except[[:space:]]*:" "$file" 2>/dev/null; then
        echo -e "${YELLOW}⚠️  Found bare 'except:' in $file${NC}"
        echo "  Use specific exception types instead"
        ((WARNINGS++))
    fi
    
    # Check for pdb imports (debugger)
    if grep -qE "import[[:space:]]+pdb|from[[:space:]]+pdb" "$file" 2>/dev/null; then
        echo -e "${RED}❌ Found pdb debugger import in $file${NC}"
        ((ERRORS++))
    fi
    
    # Check for print statements in source (not tests)
    if [[ ! "$file" =~ test ]] && [[ "$file" =~ ^(src|app)/ ]]; then
        # Look for bare print( statements (not rprint, console.print, etc)
        # This checks for print( at word boundary, not preceded by letters/dots
        if grep -E "^[^#]*[^a-zA-Z.]print\(" "$file" 2>/dev/null | grep -qv "rprint\|console\.print"; then
            echo -e "${YELLOW}⚠️  Found print() statement in source: $file${NC}"
            echo "  Use logging instead"
            ((WARNINGS++))
        fi
    fi
    
    return 0
}

# Function to check for required files
check_required_files() {
    local required_files=(
        "README.md"
        "LICENSE"
        "pyproject.toml"
        ".gitignore"
    )
    
    for req_file in "${required_files[@]}"; do
        if [ ! -f "$req_file" ]; then
            echo -e "${YELLOW}⚠️  Missing required file: $req_file${NC}"
            ((WARNINGS++))
        fi
    done
}

check_tool_schema() {
    if [ "$CHECK_TYPE" != "all" ]; then
        return 0
    fi

    if [ ! -f "$TOOL_SCHEMA_FILE" ]; then
        echo -e "${RED}❌ Missing tool schema file: $TOOL_SCHEMA_FILE${NC}"
        echo "   Run: uv run pyqa config export-tools $TOOL_SCHEMA_FILE"
        ((ERRORS++))
        return 1
    fi

    if ! command -v uv >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Skipping tool schema check (uv not installed)${NC}"
        ((WARNINGS++))
        return 0
    fi

    local tmp_schema
    tmp_schema=$(mktemp)
    if ! uv run pyqa config export-tools "$tmp_schema" >/dev/null 2>&1; then
        echo -e "${RED}❌ Failed to export tool schema via pyqa${NC}"
        ((ERRORS++))
        rm -f "$tmp_schema"
        return 1
    fi

    if ! cmp -s "$tmp_schema" "$TOOL_SCHEMA_FILE"; then
        echo -e "${RED}❌ Tool schema out of date${NC}"
        echo "   Run: uv run pyqa config export-tools $TOOL_SCHEMA_FILE"
        ((ERRORS++))
    fi

    rm -f "$tmp_schema"
}

# Main execution
echo -e "${BLUE}📋 Running code quality checks...${NC}"
echo ""

# Parse arguments
CHECK_TYPE="${1:-all}"
shift || true
FILES="$*"

# If no files specified, get staged files
if [ -z "$FILES" ] && [ "$CHECK_TYPE" != "branch" ] && [ "$CHECK_TYPE" != "commit-msg" ]; then
    FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || echo "")
fi

# Run branch protection check
#if [ "$CHECK_TYPE" = "all" ] || [ "$CHECK_TYPE" = "branch" ]; then
#    if [ -z "$SKIP_BRANCH_CHECK" ]; then
#        echo "🔒 Checking branch protection..."
#        check_branch_protection
#        echo ""
#    fi
#fi

# Check commit message if provided
if [ "$CHECK_TYPE" = "commit-msg" ] && [ -n "$1" ]; then
    echo "📝 Checking commit message format..."
    check_commit_message "$1"
    echo ""
fi

# Run file checks
if [ -n "$FILES" ]; then
    echo "📁 Checking ${CHECK_TYPE} for files..."
    
    for file in $FILES; do
        if [ ! -f "$file" ]; then
            continue
        fi
        
        if [ "$CHECK_TYPE" = "all" ] || [ "$CHECK_TYPE" = "license" ]; then
            if [[ "$file" =~ \.py$ ]]; then
                check_license_header "$file"
            fi
        fi
        
        if [ "$CHECK_TYPE" = "all" ] || [ "$CHECK_TYPE" = "size" ]; then
            check_file_size "$file"
        fi
        
        if [ "$CHECK_TYPE" = "all" ] || [ "$CHECK_TYPE" = "quality" ]; then
            check_code_quality "$file"
        fi
    done
fi

# Check for required files (only in "all" mode)
if [ "$CHECK_TYPE" = "all" ]; then
    echo "📦 Checking required files..."
    check_required_files
    check_tool_schema
    echo ""
fi

# Summary
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}❌ Quality check failed with $ERRORS error(s)${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Also found $WARNINGS warning(s)${NC}"
    fi
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Quality check passed with $WARNINGS warning(s)${NC}"
    echo "Consider addressing these warnings for better code quality"
    # Don't fail on warnings, just inform
    exit 0
else
    echo -e "${GREEN}✅ All quality checks passed!${NC}"
fi
