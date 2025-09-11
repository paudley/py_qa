#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
# Security scanning script for git-ai-reporter
# Detects potential secrets, credentials, and sensitive data in staged files

set -e

# Color codes for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Initialize findings counter
FINDINGS=0

# Function to check if a file should be excluded
should_exclude_file() {
    local file=$1
    local exclude_file=".security-check-excludes"
    
    # If excludes file doesn't exist, don't exclude anything
    if [ ! -f "$exclude_file" ]; then
        return 1
    fi
    
    # Read excludes file and check patterns
    while IFS= read -r pattern || [ -n "$pattern" ]; do
        # Skip empty lines and comments
        if [[ -z "$pattern" || "$pattern" =~ ^[[:space:]]*# ]]; then
            continue
        fi
        
        # Check if file matches the pattern
        # shellcheck disable=SC2053
        if [[ "$file" == $pattern ]]; then
            return 0  # Should exclude
        fi
        
        # Check if file matches as a glob pattern
        # shellcheck disable=SC2053
        if [[ "$file" == */$pattern ]] || [[ "$(basename "$file")" == $pattern ]]; then
            return 0  # Should exclude
        fi
    done < "$exclude_file"
    
    return 1  # Don't exclude
}

# Function to scan a file for potential secrets
scan_file() {
    local file=$1
    local found=0
    
    # Check if file should be excluded based on excludes file
    if should_exclude_file "$file"; then
        return 0
    fi
    
    # Skip the security scan script itself (contains patterns, not secrets)
    if [[ "$file" =~ security-scan\.sh$ ]]; then
        return 0
    fi
    
    # Skip lock files that contain legitimate package metadata
    if [[ "$file" =~ \.lock$ ]] || [[ "$file" =~ lock\.json$ ]] || [[ "$file" =~ yarn\.lock$ ]] || [[ "$file" =~ package-lock\.json$ ]]; then
        return 0
    fi
    
    # Skip binary files
    if file "$file" 2>/dev/null | grep -q "binary"; then
        return 0
    fi
    
    # Common patterns for secrets and credentials
    declare -a PATTERNS=(
        # API Keys and Tokens
        "api[_-]?key.*=.*['\"][a-zA-Z0-9]{20,}['\"]"
        "api[_-]?secret.*=.*['\"][a-zA-Z0-9]{20,}['\"]"
        "access[_-]?token.*=.*['\"][a-zA-Z0-9]{20,}['\"]"
        "auth[_-]?token.*=.*['\"][a-zA-Z0-9]{20,}['\"]"
        "bearer.*['\"][a-zA-Z0-9]{20,}['\"]"
        
        # AWS
        "AKIA[0-9A-Z]{16}"
        "aws[_-]?access[_-]?key[_-]?id.*=.*['\"][A-Z0-9]{20}['\"]"
        "aws[_-]?secret[_-]?access[_-]?key.*=.*['\"][a-zA-Z0-9/+=]{40}['\"]"
        
        # Google/GCP
        "AIza[0-9A-Za-z\\-_]{35}"
        "service[_-]?account.*\.json"
        
        # GitHub
        "gh[opsu]_[a-zA-Z0-9]{36}"
        "github[_-]?token.*=.*['\"][a-zA-Z0-9]{40}['\"]"
        
        # Generic Passwords
        "password.*=.*['\"][^'\"]{8,}['\"]"
        "passwd.*=.*['\"][^'\"]{8,}['\"]"
        "pwd.*=.*['\"][^'\"]{8,}['\"]"
        "secret.*=.*['\"][^'\"]{8,}['\"]"
        
        # Private Keys
        "-----BEGIN RSA PRIVATE KEY-----"
        "-----BEGIN OPENSSH PRIVATE KEY-----"
        "-----BEGIN DSA PRIVATE KEY-----"
        "-----BEGIN EC PRIVATE KEY-----"
        "-----BEGIN PGP PRIVATE KEY BLOCK-----"
        
        # Database URLs with credentials
        "postgres://[^:]+:[^@]+@"
        "mysql://[^:]+:[^@]+@"
        "mongodb://[^:]+:[^@]+@"
        "redis://[^:]+:[^@]+@"
        
        # Slack
        "xox[baprs]-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,}"
        
        # Generic Base64 encoded secrets (min 20 chars)
        "secret.*=.*['\"][A-Za-z0-9+/]{20,}={0,2}['\"]"
        
        # JWT tokens
        "eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]*"
    )
    
    # High entropy string detection (potential secrets)
    # This catches random-looking strings that might be secrets
    ENTROPY_PATTERN="['\"][a-zA-Z0-9+/]{32,}['\"]"
    
    # Check each pattern (but skip documentation files that may contain legitimate examples)
    for pattern in "${PATTERNS[@]}"; do
        if grep -qiE "$pattern" "$file" 2>/dev/null; then
            # Skip documentation files that contain environment variable examples
            if [[ "$file" =~ \.md$ ]]; then
                # Check if it's an environment variable reference (legitimate pattern in docs)
                local matches
                matches=$(grep -E "$pattern" "$file" | grep -E "os\.environ|process\.env|ENV\[|getenv\(|-e [A-Z_]+=|export [A-Z_]+=|\$\{?[A-Z_]+\}?" || true)
                if [ -n "$matches" ]; then
                    continue  # Skip environment variable references in documentation
                fi
            fi
            
            if [ $found -eq 0 ]; then
                echo -e "${RED}⚠️  Potential secrets found in $file:${NC}"
                found=1
            fi
            # Show matching lines (avoid subshell to preserve FINDINGS counter)
            grep -niE "$pattern" "$file" 2>/dev/null | head -3 | sed 's/^/  /'
            FINDINGS=$((FINDINGS + 1))
        fi
    done
    
    # Check for high entropy strings (but be less strict for test files and git hooks)
    if [[ ! "$file" =~ test_ ]] && [[ ! "$file" =~ _test\. ]] && [[ ! "$file" =~ scripts/hooks/ ]]; then
        if grep -qE "$ENTROPY_PATTERN" "$file" 2>/dev/null; then
            # Check if it's likely a real secret (not a hash or test data)
            local entropy_matches
            entropy_matches=$(grep -E "$ENTROPY_PATTERN" "$file" | \
                grep -v "sha256\|md5\|hash\|digest\|test\|example\|sample\|hexsha" | \
                grep -v "^[[:space:]]*#" | \
                grep -v "^[[:space:]]*//") || true
            
            if [ -n "$entropy_matches" ]; then
                if [ $found -eq 0 ]; then
                    echo -e "${RED}⚠️  High entropy strings found in $file:${NC}"
                    found=1
                fi
                # Show entropy matches (avoid subshell to preserve FINDINGS counter)
                echo "$entropy_matches" | head -3 | sed 's/^/  Possible secret: /' | cut -c1-80 || true
                FINDINGS=$((FINDINGS + 1))
            fi
        fi
    fi
    
    # Check for temp/backup files that shouldn't be committed
    case "$file" in
        *.bak|*.backup|*.tmp|*.temp|*.swp|*~|.env|.env.*)
            echo -e "${RED}⚠️  Temporary/backup file should not be committed: $file${NC}"
            FINDINGS=$((FINDINGS + 1))
            found=1
            ;;
    esac
    
    # Check for potential PII (Personal Identifiable Information)
    # Skip PII checks for documentation files that may contain legitimate contact info
    # Also skip GitHub Actions workflows which commonly contain legitimate git config emails
    if [[ "$file" =~ CONTRIBUTING\.md$ ]] || [[ "$file" =~ CODE_OF_CONDUCT\.md$ ]] || [[ "$file" =~ pyproject\.toml$ ]] || [[ "$file" =~ \.github/workflows/.*\.yml$ ]] || [[ "$file" =~ \.github/workflows/.*\.yaml$ ]] || [[ "$file" =~ mkdocs\.yml$ ]] || [[ "$file" =~ scripts/hooks/ ]]; then
        return $found
    fi
    
    declare -a PII_PATTERNS=(
        # SSN
        "[0-9]{3}-[0-9]{2}-[0-9]{4}"
        # Credit card (basic pattern)
        "[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}"
        # Email in code (not in comments or markdown files)
        "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    )
    
    for pattern in "${PII_PATTERNS[@]}"; do
        if grep -qE "$pattern" "$file" 2>/dev/null; then
            # Check if it's not in a comment, test file, or markdown file
            local matches
            matches=$(grep -E "$pattern" "$file" | \
                grep -v "^[[:space:]]*#" | \
                grep -v "^[[:space:]]*//") || true
            
            # Skip email check for markdown files (documentation)
            if [ -n "$matches" ] && [[ ! "$file" =~ test ]] && [[ ! "$file" =~ \.md$ ]]; then
                if [ $found -eq 0 ]; then
                    echo -e "${YELLOW}⚠️  Potential PII found in $file${NC}"
                    found=1
                fi
            fi
        fi
    done
    
    return $found
}

# Function to run bandit security analysis
run_bandit_scan() {
    echo "🛡️  Running bandit security analysis..."
    
    # Create a temporary bandit report file
    local bandit_report
    bandit_report=$(mktemp)
    
    # Run bandit on src/ directory using pyproject.toml configuration
    if [ ! -d "src/" ]; then
        echo "  No src/ directory found, skipping bandit scan"
        return 0
    fi
    
    # Run bandit with JSON output for parsing
    if uv run bandit -r src/ -f json -o "$bandit_report" --quiet 2>/dev/null; then
        echo "  ✅ Bandit scan completed - no security issues found"
        rm -f "$bandit_report"
        return 0
    else
        local exit_code=$?
        if [ $exit_code -eq 1 ]; then
            # Bandit found issues
            echo -e "  ${RED}⚠️  Bandit found security vulnerabilities:${NC}"
            
            # Parse JSON output for human-readable summary
            if command -v jq >/dev/null 2>&1; then
                # Use jq if available for better parsing
                local high_severity
                local medium_severity
                local low_severity
                high_severity=$(jq -r '.metrics._totals."SEVERITY.HIGH" // 0' "$bandit_report")
                medium_severity=$(jq -r '.metrics._totals."SEVERITY.MEDIUM" // 0' "$bandit_report")
                low_severity=$(jq -r '.metrics._totals."SEVERITY.LOW" // 0' "$bandit_report")
                
                echo -e "    ${RED}High severity: $high_severity${NC}"
                echo -e "    ${YELLOW}Medium severity: $medium_severity${NC}"
                echo -e "    Low severity: $low_severity"
                
                # Show first few issues for context
                echo ""
                echo "  Sample issues found:"
                jq -r '.results[:3][] | "    \(.filename):\(.line_number) - \(.issue_text)"' "$bandit_report" 2>/dev/null | head -5
            else
                # Fallback to basic parsing without jq
                echo "  See detailed report for security issues"
                grep -o '"SEVERITY\.[^"]*":[0-9]*' "$bandit_report" 2>/dev/null | head -5 || echo "  Run bandit manually for details"
            fi
            
            echo ""
            echo -e "  ${YELLOW}To view full bandit report:${NC}"
            echo "    uv run bandit -r src/ --format screen"
            echo ""
            
            rm -f "$bandit_report"
            FINDINGS=$((FINDINGS + 10))  # Add to findings counter
            return 1
        else
            # Other error (e.g., syntax error, missing files)
            echo -e "  ${YELLOW}⚠️  Bandit scan encountered an error (exit code: $exit_code)${NC}"
            rm -f "$bandit_report"
            return 0  # Don't fail the entire scan for bandit errors
        fi
    fi
}

# Main execution
echo "🔒 Running comprehensive security scan..."

# Get list of files to scan (passed as arguments or from git)
if [ $# -gt 0 ]; then
    FILES="$*"
else
    # Get staged files if no arguments
    FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || echo "")
fi

if [ -z "$FILES" ]; then
    echo "No files to scan"
    exit 0
fi

# Run bandit analysis first (for Python security vulnerabilities)
run_bandit_scan

echo ""
echo "🔍 Scanning files for secrets and credentials..."

# Scan each file
for file in $FILES; do
    if [ -f "$file" ]; then
        scan_file "$file"
    fi
done

# Summary
echo ""
if [ $FINDINGS -gt 0 ]; then
    echo -e "${RED}❌ Security scan found $FINDINGS potential issue(s)${NC}"
    echo ""
    echo "If these are false positives, you can:"
    echo "  1. Move secrets to environment variables"
    echo "  2. Use a .env file (and add it to .gitignore)"
    echo "  3. Use a secrets management service"
    echo "  4. If it's test data, ensure it's clearly marked as such"
    echo ""
else
    echo -e "${GREEN}✅ Security scan passed - no secrets detected${NC}"
fi
