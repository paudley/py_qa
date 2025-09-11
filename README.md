# SPECTRA Extraction Scripts

This directory contains simple wrapper scripts for easy command-line access to the SPECTRA extraction system.

## Scripts

### `extract.py` - Python Wrapper
Simple Python script that imports and runs the SPECTRA CLI with proper path setup.

```bash
# Make executable
chmod +x scripts/extract.py

# Usage examples
./scripts/extract.py --help
./scripts/extract.py extract gwp
./scripts/extract.py extract gpss --comprehensive
python scripts/extract.py validate schema.json
```

### `extract.sh` - Bash Wrapper  
Simple bash script that calls the Python module with proper environment setup.

```bash
# Make executable
chmod +x scripts/extract.sh

# Usage examples
./scripts/extract.sh --help
./scripts/extract.sh extract gwp
./scripts/extract.sh extract gpss --comprehensive
bash scripts/extract.sh validate schema.json
```

### `extract_gwp.py` - GWP Legacy Wrapper
Backwards compatibility wrapper for GWP extraction. Now uses the unified pipeline internally.

```bash
# Traditional GWP extraction interface
python scripts/extract_gwp.py --source-dir datasets/gwp --output-dir datasets/gwp/extracted

# For new projects, prefer the generic wrappers:
./scripts/extract.py extract gwp --source-dir datasets/gwp --output-dir datasets/gwp/extracted
```

## Available Commands

The wrapper scripts provide access to all SPECTRA CLI commands:

- `extract <dataset>` - Extract dataset using comprehensive pipeline
- `validate <schema.json>` - Validate SPECTRA schema
- `score <schema.json>` - Score schema quality  
- `enhance <schema.json>` - Enhance existing schema
- `transform <data.xlsx>` - Transform Excel to SPECTRA
- `create <dataset.parquet>` - Create new schema from dataset
- `analyze <schema.json>` - Analyze schema completeness

## Examples

```bash
# Extract GWP dataset
./scripts/extract.sh extract gwp --verbose

# Validate a SPECTRA schema
./scripts/extract.py validate my_schema.json --strict

# Score schema quality
./scripts/extract.sh score my_schema.json --detailed

# Transform Excel file to SPECTRA
./scripts/extract.py transform data.xlsx -o schema.json

# Create schema from Parquet file
./scripts/extract.sh create dataset.parquet -n "My Dataset"
```

## Error Handling

Both wrapper scripts include:
- Path validation for the spectra-schema package
- Proper error reporting and exit codes
- Environment variable handling for Python path
- Working directory management

If you encounter import errors, ensure that all dependencies are installed in your Python environment.