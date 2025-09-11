#!/bin/bash
# SPDX-License-Identifier: MIT
# Comprehensive pyreadstat UTF-8 patch solution for complexify
# This script handles the complete process: download, patch, build, install
set -e

echo "=============================================================================="
echo "COMPLEXIFY PYREADSTAT UTF-8 PATCH SOLUTION"
echo "=============================================================================="

SCRIPT_DIR="$(pwd)/$(dirname "$0")"
SOURCE_DIR="$SCRIPT_DIR/pyreadstat_source"
PATCH_DIR="$SCRIPT_DIR"

echo "📂 Working in: $SCRIPT_DIR"

# Step 1: Ensure pyreadstat source exists
if [ ! -d "$SOURCE_DIR" ]; then
    echo "📥 Step 1: Downloading pyreadstat source..."
    cd "$SCRIPT_DIR"
    git clone https://github.com/Roche/pyreadstat.git pyreadstat_source
    echo "✅ Source downloaded"
else
    echo "✅ Step 1: Source already exists"
fi

cd "$SOURCE_DIR"

# Step 2: Clean any previous builds
echo "🧹 Step 2: Cleaning previous builds..."
rm -rf build/ dist/ *.egg-info/
python setup.py clean --all 2>/dev/null || true

# Step 3: Install build dependencies in complexify environment
echo "📦 Step 3: Ensuring build dependencies..."
cd ../../../  # Back to complexify root
if ! uv run python -c "import cython" 2>/dev/null; then
    echo "   Installing cython..."
    uv add cython
fi
if ! uv run python -c "import setuptools" 2>/dev/null; then
    echo "   Installing setuptools..."  
    uv add setuptools
fi
echo "✅ Build dependencies ready"

cd "$SOURCE_DIR"

# Step 4: Generate C files with Cython
echo "🔧 Step 4: Generating C files with Cython..."
uv run python setup.py build_ext --inplace

# Step 5: Apply UTF-8 patches to generated C files
echo "🩹 Step 5: Applying UTF-8 patches..."

# Apply patches using sed for reliability
patch_files=(
    "pyreadstat/_readstat_parser.c"
    "pyreadstat/_readstat_writer.c"
    "pyreadstat/pyreadstat.c"
)

patch_count=0
for file in "${patch_files[@]}"; do
    if [ -f "$file" ]; then
        echo "   Patching $file..."
        # Replace strict UTF-8 decoding with error-tolerant version
        if sed -i 's/PyUnicode_DecodeUTF8(c_str, size, NULL)/PyUnicode_DecodeUTF8(c_str, size, "replace")/g' "$file"; then
            patch_count=$((patch_count + 1))
            echo "   ✅ Patched $file"
        else
            echo "   ❌ Failed to patch $file"
        fi
    else
        echo "   ⚠️  File not found: $file"
    fi
done

if [ $patch_count -eq 0 ]; then
    echo "❌ No patches applied!"
    exit 1
fi

echo "✅ Applied patches to $patch_count files"

# Step 6: Verify patches were applied
echo "🔍 Step 6: Verifying patches..."
if grep -q 'PyUnicode_DecodeUTF8.*"replace"' pyreadstat/_readstat_parser.c; then
    echo "✅ Patches verified in C files"
else
    echo "❌ Patches not found in C files"
    exit 1
fi

# Step 7: Install the patched version in complexify
echo "📦 Step 7: Installing patched pyreadstat in complexify..."
cd ~/Active/tcomp  # Back to complexify root
uv pip install "./py-qa/pyreadstat_patch/pyreadstat_source" --force-reinstall --no-build-isolation

# Step 8: Validation test
echo "🧪 Step 8: Validation test..."
uv run python -c "
import pyreadstat
print('✅ Patched pyreadstat imported successfully')
print(f'   Version: {pyreadstat.__version__}')

# Test on the problematic SAV file
try:
    df, meta = pyreadstat.read_sav('datasets/gwp/Gallup_World_Poll_022125.sav', metadataonly=True)
    print(f'✅ SUCCESS! SAV file metadata read: {len(meta.column_names)} variables')
    print(f'   File encoding: {meta.file_encoding}')
    print(f'   Sample variables: {meta.column_names[:3]}')
    
    # Test a small data sample
    df_sample, _ = pyreadstat.read_sav('datasets/gwp/Gallup_World_Poll_022125.sav', row_limit=10)
    print(f'✅ SUCCESS! Data sample read: {df_sample.shape}')
    
except Exception as e:
    print(f'❌ Validation failed: {e}')
    exit 1
"

echo ""
echo "=============================================================================="
echo "🎉 PATCHED PYREADSTAT SUCCESSFULLY INSTALLED IN COMPLEXIFY!"
echo "🎉 SAV files with UTF-8 encoding issues can now be processed!"
echo "=============================================================================="
echo ""
echo "The patch resolves the UTF-8 encoding error by using 'replace' error handling"
echo "instead of strict UTF-8 decoding. Invalid bytes like 0x9a are replaced with '�'."
echo ""
echo "You can now run your SAV extraction scripts successfully."
