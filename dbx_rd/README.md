# dbx_rd — Databricks R&D Prototyping

Prototyping directory for the neo4j-graphrag-python migration. Contains shell scripts that upload, validate, and run Python scripts on a remote Databricks cluster from the local terminal.

## Setup

All scripts read from `.env` in this directory. The required variables are:

- `DATABRICKS_PROFILE` — name of the CLI profile (configured via `databricks configure --profile <name>`)
- `DATABRICKS_CLUSTER_ID` — ID of an existing all-purpose cluster to run jobs on
- `WORKSPACE_DIR` — remote workspace path where scripts are uploaded

The cluster must be running or in a state where it can auto-start. Check status with:

```bash
databricks clusters list --profile azure-rk-knight
```

## Scripts

### upload.sh — Upload Python files to the workspace

Uploads local `.py` files to the remote `WORKSPACE_DIR`. Creates the remote directory if it doesn't exist.

```bash
./upload.sh                    # upload test_hello.py (default)
./upload.sh my_script.py       # upload a specific file
./upload.sh --all              # upload all .py files in this directory
```

Under the hood this runs:
- `databricks workspace mkdirs` to ensure the remote directory exists
- `databricks workspace import --file <local> --format AUTO --language PYTHON --overwrite <remote>`

### validate.sh — Verify uploads landed

Lists the contents of the remote workspace directory to confirm files are there.

```bash
./validate.sh                  # list all files in the remote directory
./validate.sh test_hello.py    # check a specific file exists
```

### submit.sh — Run a script on the cluster

Submits a one-time job run using `databricks jobs submit`. The job uses `spark_python_task` pointed at the uploaded workspace file and runs on the existing cluster from `.env`. The CLI waits for the job to finish and prints the result JSON.

```bash
./submit.sh                         # run test_hello.py (default)
./submit.sh my_script.py            # run a specific script
./submit.sh my_script.py --no-wait  # submit without waiting for completion
```

The job is not saved — it runs once and does not appear in the Databricks Jobs UI. Output can be retrieved after the fact with:

```bash
databricks jobs get-run-output <TASK_RUN_ID> --profile azure-rk-knight -o json
```

Note: use the task-level `run_id` from the `tasks` array in the submit output, not the top-level `run_id`.

## Typical iteration loop

```bash
# 1. Edit a Python script locally
# 2. Upload and run
./upload.sh my_script.py && ./submit.sh my_script.py

# Or upload everything and run one
./upload.sh --all && ./submit.sh my_script.py
```

On a running cluster, the full cycle (upload + submit + execute + return output) takes under a minute for small scripts.

## What was verified (Phase 1)

The test script `test_hello.py` confirmed the following are available on the cluster:

| Component | Version |
|-----------|---------|
| Databricks Runtime | 17.3 |
| Python | 3.12.3 |
| Spark | 4.0.0 |
| mlflow | 3.10.1 |
| neo4j driver | 6.1.0 |

All dependencies needed for Phase 2 (Databricks adapter classes) are pre-installed on the cluster.
