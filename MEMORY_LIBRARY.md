# Packaging neo4j-agent-memory for Databricks

This guide explains how to package the `neo4j-agent-memory` library — currently installed from a local `maf`-branch checkout — as a Python wheel and make it available on a Databricks cluster or Model Serving endpoint.

## Library facts

| Fact | Value |
|---|---|
| Source location | `../agent-memory` (sibling directory) |
| GitHub repo | `https://github.com/neo4j-labs/agent-memory` |
| Branch | `maf` (not published to PyPI — must be built locally) |
| Package name | `neo4j-agent-memory` |
| Import name | `neo4j_agent_memory` |
| Version | `0.0.1` |
| Build backend | `hatchling` |
| Wheel type | Pure Python (`py3-none-any`) — no native extensions |
| Required extras | `[openai,langchain]` |
| Core dependencies | `neo4j>=5.20.0`, `pydantic>=2.0.0`, `pydantic-settings>=2.0.0` |
| `openai` extra adds | `openai>=1.0.0` |
| `langchain` extra adds | `langchain-core>=0.2.0` |

---

## Part 1: Building the wheel locally

### Verify you are on the correct branch

```bash
cd ../agent-memory
git branch --show-current
# must print: maf
```

### Build with make (recommended)

The Makefile defines `make build` as `clean` then `uv build`:

```bash
cd ../agent-memory
make build
```

Expected output:

```
Successfully built dist/neo4j_agent_memory-0.0.1.tar.gz
Successfully built dist/neo4j_agent_memory-0.0.1-py3-none-any.whl
```

The `py3-none-any` tag means the same wheel runs on any Python 3 interpreter on any OS.

### Confirm the wheel

```bash
ls -lh dist/neo4j_agent_memory-0.0.1-py3-none-any.whl
```

---

## Part 2: Installing on a Databricks cluster

Three methods, ordered from most durable to most ad-hoc. Use Method A for production. Use Method C during rapid iteration in notebooks.

### Method A: Upload to Unity Catalog Volume + cluster library

#### A1: Upload the wheel

Using the Databricks CLI:

```bash
databricks fs cp \
  ../agent-memory/dist/neo4j_agent_memory-0.0.1-py3-none-any.whl \
  dbfs:/Volumes/retail_assistant/retail/retail_volume/libs/neo4j_agent_memory-0.0.1-py3-none-any.whl
```

Or using the Databricks SDK (consistent with the existing `lakehouse_tables.py` pattern):

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
with open("../agent-memory/dist/neo4j_agent_memory-0.0.1-py3-none-any.whl", "rb") as f:
    w.files.upload(
        "/Volumes/retail_assistant/retail/retail_volume/libs/neo4j_agent_memory-0.0.1-py3-none-any.whl",
        f,
        overwrite=True,
    )
```

#### A2: Install as a cluster library

1. Go to **Compute** in the left sidebar
2. Click your cluster > **Libraries** tab > **Install new**
3. Source: **Volumes** — browse to the wheel file
4. Click **Install**, then restart the cluster

#### A3: Install the extras

The cluster library install only installs base dependencies. Add these as additional **PyPI** libraries in the same cluster library UI:

- `openai>=1.0.0`
- `langchain-core>=0.2.0`

### Method B: Cluster init script

Create `cluster-init-retail-assistant.sh`:

```bash
#!/bin/bash
set -euo pipefail

WHEEL_PATH="/Volumes/retail_assistant/retail/retail_volume/libs/neo4j_agent_memory-0.0.1-py3-none-any.whl"

pip install --quiet \
  "$WHEEL_PATH" \
  "openai>=1.0.0" \
  "langchain-core>=0.2.0"
```

Upload and register:

```bash
databricks fs cp cluster-init-retail-assistant.sh dbfs:/init-scripts/retail-assistant/
```

Then in Cluster settings > **Advanced options** > **Init scripts**, add:
`dbfs:/init-scripts/retail-assistant/cluster-init-retail-assistant.sh`

### Method C: %pip install in a notebook (development only)

```python
# From a pre-uploaded wheel
%pip install \
  /Volumes/retail_assistant/retail/retail_volume/libs/neo4j_agent_memory-0.0.1-py3-none-any.whl \
  "openai>=1.0.0" \
  "langchain-core>=0.2.0"

# Or directly from GitHub (requires network access)
%pip install "neo4j-agent-memory[openai,langchain] @ git+https://github.com/neo4j-labs/agent-memory.git@maf"

# Restart the Python interpreter after install
dbutils.library.restartPython()
```

The `git+https://...@maf` form always pulls the latest commit — convenient for dev, but non-deterministic.

---

## Part 3: Including in MLflow Model Serving

This is the key section for the `deploy.py` pipeline described in `LANGCHAIN_AGENT.md`.

### Recommended: Bundle the wheel via code_paths

Include the wheel in `code_paths` so MLflow copies it into the model artifact under `code/`. At serving time, MLflow installs it from that local path — no internet access to GitHub or PyPI needed.

```python
import mlflow
from pathlib import Path

WHEEL_NAME = "neo4j_agent_memory-0.0.1-py3-none-any.whl"
WHEEL_PATH = str(Path("../agent-memory/dist") / WHEEL_NAME)

with mlflow.start_run():
    logged = mlflow.langchain.log_model(
        lc_model="./backend/databricks_agent/serving.py",
        name="neo4j_kg_agent",
        code_paths=[
            WHEEL_PATH,       # wheel bundled into artifact
            "./backend",      # source code for tools and agent
        ],
        pip_requirements=[
            "mlflow>=3.1",
            "langgraph>=1.0.8",
            "langchain-core>=0.3.0",
            "databricks-langchain>=0.15.0",
            "neo4j>=5.20.0",
            "pydantic>=2.0.0",
            "pydantic-settings>=2.0.0",
            "openai>=1.0.0",
        ],
        extra_pip_requirements=[
            f"code/{WHEEL_NAME}",  # install from bundled copy
        ],
    )
```

The serving container receives the wheel at `code/neo4j_agent_memory-0.0.1-py3-none-any.whl` and `pip install`s it automatically.

### Alternative: Reference from Unity Catalog Volume

If the wheel is already uploaded (Part 2), reference it directly:

```python
pip_requirements=[
    ...,
    "/Volumes/retail_assistant/retail/retail_volume/libs/neo4j_agent_memory-0.0.1-py3-none-any.whl",
]
```

This is simpler but creates an external dependency — if the Volume path changes, the model breaks. The `code_paths` approach bundles everything into a self-contained artifact.

---

## Part 4: Important considerations

### Extras and transitive dependencies

When installing from a wheel file path, extras syntax (`[openai,langchain]`) is not universally supported by all pip versions. The safest practice — used throughout this guide — is to list `openai` and `langchain-core` as explicit entries in `pip_requirements` alongside the wheel.

### Rebuild workflow

After any change to the library source, the wheel must be rebuilt and the MLflow model re-logged:

```bash
# 1. Pull latest maf branch
cd ../agent-memory
git pull origin maf

# 2. Rebuild
make build

# 3. Re-deploy
cd ../databricks-retail-assistant
uv run python -m backend.databricks_agent.deploy
```

If only the retail assistant code changed (not the library), skip steps 1–2.

### The maf branch

The `maf` branch contains the Microsoft Agent Framework integration. It exposes the same `MemoryClient`, `MemorySettings`, and LangChain integration the retail assistant relies on. Do not confuse it with `main`, which may have a different API surface. The branch is not published to PyPI — the wheel-based install documented here is required for Databricks.

### Python version compatibility

The library declares `requires-python = ">=3.10"`. Databricks Runtime 15.x uses Python 3.11; Runtime 16.x uses Python 3.12. Both are compatible. The `py3-none-any` wheel tag signals compatibility with any Python 3.

### Verifying the install on a cluster

```python
from neo4j_agent_memory import MemoryClient, MemorySettings
from neo4j_agent_memory.integrations.langchain import Neo4jAgentMemory
import openai
import langchain_core
print("neo4j-agent-memory loaded successfully")
```

---

## Quick reference

```bash
# Build
cd ../agent-memory && git checkout maf && git pull origin maf && make build

# Upload (optional — only needed for cluster library method)
databricks fs cp \
  dist/neo4j_agent_memory-0.0.1-py3-none-any.whl \
  dbfs:/Volumes/retail_assistant/retail/retail_volume/libs/neo4j_agent_memory-0.0.1-py3-none-any.whl

# Deploy to Model Serving (wheel bundled into MLflow artifact via code_paths)
cd ../databricks-retail-assistant && uv run python -m backend.databricks_agent.deploy
```
