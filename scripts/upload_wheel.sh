#!/usr/bin/env bash
set -euo pipefail

WHEEL="neo4j_agent_memory-0.0.1-py3-none-any.whl"
VOLUME_PATH="/Volumes/retail_assistant/retail/retail_volume/libs/${WHEEL}"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <databricks-profile>"
  echo "Example: $0 my-profile"
  exit 1
fi

PROFILE="$1"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WHEEL_FILE="${REPO_ROOT}/dist/${WHEEL}"

if [[ ! -f "$WHEEL_FILE" ]]; then
  echo "Error: ${WHEEL} not found in ${SCRIPT_DIR}"
  echo "Run 'make build' in the agent-memory directory first, then copy the wheel here."
  exit 1
fi

echo "Uploading ${WHEEL} to ${VOLUME_PATH} (profile: ${PROFILE})..."
databricks fs cp --profile "$PROFILE" --overwrite \
  "$WHEEL_FILE" \
  "dbfs:${VOLUME_PATH}"

echo "Done. Wheel uploaded to ${VOLUME_PATH}"
