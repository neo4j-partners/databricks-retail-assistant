#!/usr/bin/env bash
# Submit a Python script as a one-time Databricks job run.
#
# Usage:
#   ./submit.sh                         # runs test_hello.py (default)
#   ./submit.sh my_script.py            # runs a specific uploaded script
#   ./submit.sh my_script.py --no-wait  # submit without waiting for completion
#
# The script must already be uploaded via ./upload.sh.
# Uses an existing cluster (DATABRICKS_CLUSTER_ID from .env) for fast iteration.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env
set -a
source "$SCRIPT_DIR/.env"
set +a

PROFILE="$DATABRICKS_PROFILE"
REMOTE_DIR="$WORKSPACE_DIR"
CLUSTER_ID="$DATABRICKS_CLUSTER_ID"

SCRIPT_NAME="${1:-test_hello.py}"
NO_WAIT=""
if [[ "${2:-}" == "--no-wait" ]]; then
    NO_WAIT="--no-wait"
fi

REMOTE_PATH="$REMOTE_DIR/$SCRIPT_NAME"
RUN_NAME="dbx_rd: $SCRIPT_NAME"

echo "Submitting job (profile: $PROFILE)"
echo "  Script: $REMOTE_PATH"
echo "  Cluster: $CLUSTER_ID"
echo "  Run name: $RUN_NAME"
echo "---"

# Build the job JSON.
# Uses an existing all-purpose cluster for fast iteration (no startup wait).
JOB_JSON=$(cat <<EOF
{
  "run_name": "$RUN_NAME",
  "tasks": [
    {
      "task_key": "run_script",
      "spark_python_task": {
        "python_file": "$REMOTE_PATH"
      },
      "existing_cluster_id": "$CLUSTER_ID"
    }
  ]
}
EOF
)

databricks jobs submit \
    --profile "$PROFILE" \
    --json "$JOB_JSON" \
    $NO_WAIT

echo ""
echo "Job submission complete."
