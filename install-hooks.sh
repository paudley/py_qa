#!/bin/bash
# Install git hooks for the git-ai-reporter project
# This script sets up pre-commit and pre-push hooks to ensure code quality

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$PROJECT_ROOT/.git/hooks"

echo "📦 Installing Git hooks for git-ai-reporter..."
echo ""

# Function to create a hook
install_hook() {
    local hook_name=$1
    local hook_file="$HOOKS_DIR/$hook_name"
    local template_file="$PROJECT_ROOT/scripts/hooks/$hook_name"
    
    if [ -f "$hook_file" ] && [ ! -L "$hook_file" ]; then
        echo "⚠️  Existing $hook_name hook found. Creating backup..."
        mv "$hook_file" "$hook_file.backup.$(date +%Y%m%d_%H%M%S)"
    fi
    
    # Create symlink to the hook template
    if [ -f "$template_file" ]; then
        ln -sf "$template_file" "$hook_file"
        chmod +x "$hook_file"
        echo "✅ Installed $hook_name hook"
    else
        echo "⚠️  Template for $hook_name not found at $template_file"
    fi
}

# Check if we're in a git repository
if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo "❌ Error: Not in a git repository!"
    echo "Please run this script from the git-ai-reporter project root."
    exit 1
fi

# Create hooks directory if it doesn't exist
mkdir -p "$HOOKS_DIR"

# Install hooks
install_hook "pre-commit"
install_hook "pre-push"
install_hook "commit-msg"

echo ""
echo "🎉 Git hooks installed successfully!"
echo ""
echo "The following checks will now run automatically:"
echo "  📝 Pre-commit:"
echo "     • Security scanning for credentials and secrets"
echo "     • License header validation"
echo "     • File size limits check"
echo "     • Code formatting (ruff format)"
echo "     • Linting (ruff check)"
echo "     • Type checking (mypy)"
echo "     • Debug statement detection"
echo ""
echo "  📋 Commit-msg:"
echo "     • Conventional commit format validation"
echo "     • Commit message length check"
echo ""
echo "  🚀 Pre-push:"
echo "     • Branch protection (no direct push to main/master)"
echo "     • Comprehensive security scan"
echo "     • Full lint check (./scripts/lint.sh)"
echo "     • Test suite with comprehensive coverage requirement"
echo ""
echo "To uninstall hooks:"
echo "  • rm .git/hooks/pre-commit .git/hooks/pre-push"
