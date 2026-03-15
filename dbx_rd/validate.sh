#!/usr/bin/env bash
# Validate that files were uploaded to the Databricks workspace.
#
# Usage:
#   ./validate.sh                  # lists all files in the remote dbx_rd/ dir
#   ./validate.sh test_hello.py    # checks a specific file exists

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env
set -a
source "$SCRIPT_DIR/.env"
set +a

PROFILE="$DATABRICKS_PROFILE"
REMOTE_DIR="$WORKSPACE_DIR"
CLUSTER_ID="$DATABRICKS_CLUSTER_ID"

# shellcheck source=cluster_utils.sh
source "$SCRIPT_DIR/cluster_utils.sh"

echo "Listing workspace: $REMOTE_DIR (profile: $PROFILE)"
ensure_cluster_running "$PROFILE" "$CLUSTER_ID"
echo "---"

if ! databricks workspace list --profile "$PROFILE" "$REMOTE_DIR" 2>/dev/null; then
    echo "Error: Remote directory $REMOTE_DIR does not exist."
    echo "Run ./upload.sh first to create it."
    exit 1
fi

# If a specific file was requested, check it exists
if [[ -n "${1:-}" ]]; then
    echo ""
    echo "Checking: $REMOTE_DIR/$1"
    if databricks workspace get-status --profile "$PROFILE" "$REMOTE_DIR/$1" 2>/dev/null; then
        echo "  Found."
    else
        echo "  Not found."
        exit 1
    fi
fi

echo ""
echo "Validation complete."
