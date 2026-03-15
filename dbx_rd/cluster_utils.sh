#!/usr/bin/env bash
# Shared cluster utilities for dbx_rd scripts.
# Source this file after loading .env and setting PROFILE and CLUSTER_ID.

# Check cluster state and start it if terminated.
# Waits for the cluster to reach RUNNING state before returning.
# Exits with code 1 if the cluster cannot be started.
ensure_cluster_running() {
    local profile="$1"
    local cluster_id="$2"
    local poll_interval=15
    local max_wait=600  # 10 minutes

    # Get current cluster state
    local state
    state=$(databricks clusters get --profile "$profile" "$cluster_id" 2>/dev/null \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('state','UNKNOWN'))" 2>/dev/null) \
        || { echo "Error: Could not get cluster state for $cluster_id"; exit 1; }

    echo "  Cluster:  $cluster_id ($state)"

    case "$state" in
        RUNNING)
            return 0
            ;;
        TERMINATED)
            echo "  Starting cluster..."
            databricks clusters start --profile "$profile" "$cluster_id" 2>/dev/null \
                || { echo "Error: Failed to start cluster $cluster_id"; exit 1; }
            ;;
        PENDING|RESIZING|RESTARTING)
            echo "  Cluster is $state, waiting..."
            ;;
        TERMINATING)
            echo "  Cluster is terminating, waiting for it to stop before restarting..."
            ;;
        ERROR)
            echo "Error: Cluster $cluster_id is in ERROR state."
            exit 1
            ;;
        *)
            echo "Error: Cluster $cluster_id is in unexpected state: $state"
            exit 1
            ;;
    esac

    # Poll until RUNNING
    local elapsed=0
    while [[ $elapsed -lt $max_wait ]]; do
        state=$(databricks clusters get --profile "$profile" "$cluster_id" 2>/dev/null \
            | python3 -c "import json,sys; print(json.load(sys.stdin).get('state','UNKNOWN'))" 2>/dev/null) \
            || state="UNKNOWN"

        case "$state" in
            RUNNING)
                echo "  Cluster is running."
                return 0
                ;;
            TERMINATED)
                # Was TERMINATING, now terminated — start it
                echo "  Starting cluster..."
                databricks clusters start --profile "$profile" "$cluster_id" 2>/dev/null || true
                ;;
            PENDING|RESIZING|RESTARTING)
                ;;
            ERROR)
                echo "Error: Cluster entered ERROR state."
                exit 1
                ;;
        esac

        sleep "$poll_interval"
        elapsed=$((elapsed + poll_interval))
        echo "  Waiting for cluster... ${elapsed}s elapsed ($state)"
    done

    echo "Error: Cluster did not reach RUNNING state within ${max_wait}s."
    exit 1
}
