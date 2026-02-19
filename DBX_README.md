# Databricks Quick Start

This project depends on `neo4j-agent-memory`, a library not published to PyPI. These steps build it as a wheel and install it on a Databricks cluster.

## Prerequisites

- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/index.html) installed and configured with a profile (`databricks configure --profile <name>`)
- A Databricks cluster with access to the Unity Catalog volume `retail_assistant.retail.retail_volume`

## Cluster library versions

Install these as **PyPI** libraries on the cluster. Avoid duplicates — if an older version is already installed, uninstall it first.

| Library | Version | Source | Notes |
|---|---|---|---|
| `neo4j-agent-memory` | `0.0.1` | Wheel (Volume) | Built from `maf` branch — see Steps 1–3 below |
| `neo4j` | `5.27.0` | PyPI | The agent-memory library requires `>=5.20.0`. Use 5.x, not 6.x — the neo4j 6.x driver has breaking API changes that may conflict with agent-memory |
| `langgraph` | `0.4.1` | PyPI | Latest 0.x stable. The 1.x line is pre-release |
| `langchain-core` | `0.3.51` | PyPI | Latest 0.3.x stable. The 1.x line is pre-release and may have breaking changes |
| `langchain-openai` | `0.3.18` | PyPI | Must match the langchain-core 0.3.x line |
| `openai` | `1.82.0` | PyPI | Required by agent-memory `[openai]` extra |
| `pydantic` | `2.12.5` | PyPI | |
| `pydantic-settings` | `2.13.0` | PyPI | |
| `databricks-agents` | `1.9.3` | PyPI | |
| `databricks-langchain` | `0.15.0` | PyPI | |
| `neo4j-graphrag` | `1.13.0` | PyPI | |

> **Why not the "latest" 1.x versions of langgraph/langchain-core/langchain-openai?**
> PyPI shows `langgraph==1.0.8`, `langchain-core==1.2.13`, `langchain-openai==1.1.10` as "latest", but these are part of a recent major version bump that introduced breaking changes. The 0.x / 0.3.x lines are the current stable releases that the broader LangChain ecosystem (including `databricks-langchain`) is pinned against. Installing 1.x versions alongside 0.x dependencies causes pip resolution failures — which is why you saw neo4j, langgraph, and langchain-openai failing to resolve.

## Step 1: Build the wheel

The library lives in a sibling checkout on the `maf` branch:

```bash
cd ../agent-memory
git checkout maf
git pull origin maf
make build
```

This produces `dist/neo4j_agent_memory-0.0.1-py3-none-any.whl`.

Copy the wheel into this project's `dist/` directory:

```bash
cp ../agent-memory/dist/neo4j_agent_memory-0.0.1-py3-none-any.whl dist/
```

## Step 2: Upload the wheel to Databricks

Use the included upload script, passing your Databricks CLI profile name:

```bash
./dist/upload_wheel.sh <databricks-profile>
```

This uploads the wheel to `/Volumes/retail_assistant/retail/retail_volume/libs/`.

## Step 3: Install as a cluster library

1. In the Databricks workspace, go to **Compute** in the left sidebar
2. Click your cluster > **Libraries** tab > **Install new**
3. Select source: **Volumes**
4. Browse to `retail_assistant` > `retail` > `retail_volume` > `libs` > `neo4j_agent_memory-0.0.1-py3-none-any.whl`
5. Click **Install**

Then add the PyPI libraries from the table above (same **Install new** dialog, select **PyPI** as the source). Install each one individually.

Restart the cluster.

## Verify

In a notebook attached to the cluster:

```python
from neo4j_agent_memory import MemoryClient, MemorySettings
from neo4j_agent_memory.integrations.langchain import Neo4jAgentMemory
import openai
import langchain_core
print("neo4j-agent-memory loaded successfully")
```
