#!/usr/bin/env bash
# Upload Python files from dbx_rd/ to the Databricks workspace.
#
# Usage:
#   ./upload.sh                    # uploads test_hello.py (default)
#   ./upload.sh my_script.py       # uploads a specific file
#   ./upload.sh --all              # uploads all .py files in dbx_rd/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env
set -a
source "$SCRIPT_DIR/.env"
set +a

PROFILE="$DATABRICKS_PROFILE"
REMOTE_DIR="$WORKSPACE_DIR"

# Ensure remote directory exists
databricks workspace mkdirs --profile "$PROFILE" "$REMOTE_DIR" 2>/dev/null || true

upload_file() {
    local local_file="$1"
    local filename
    filename="$(basename "$local_file")"
    local remote_path="$REMOTE_DIR/$filename"

    echo "Uploading: $filename -> $remote_path"
    databricks workspace import \
        --profile "$PROFILE" \
        --file "$local_file" \
        --format AUTO \
        --language PYTHON \
        --overwrite \
        "$remote_path"
    echo "  Done."
}

# Parse arguments
if [[ "${1:-}" == "--all" ]]; then
    echo "Uploading all .py files to $REMOTE_DIR (profile: $PROFILE)"
    echo "---"
    for f in "$SCRIPT_DIR"/*.py; do
        [[ -f "$f" ]] && upload_file "$f"
    done
elif [[ -n "${1:-}" ]]; then
    local_path="$SCRIPT_DIR/$1"
    if [[ ! -f "$local_path" ]]; then
        echo "Error: $local_path not found"
        exit 1
    fi
    echo "Uploading to $REMOTE_DIR (profile: $PROFILE)"
    echo "---"
    upload_file "$local_path"
else
    echo "Uploading test_hello.py to $REMOTE_DIR (profile: $PROFILE)"
    echo "---"
    upload_file "$SCRIPT_DIR/test_hello.py"
fi

echo ""
echo "Upload complete."
