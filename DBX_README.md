# Databricks Quick Start

This project depends on `neo4j-agent-memory`, a library not published to PyPI. These steps build it as a wheel and install it on a Databricks cluster.

## Prerequisites

- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/index.html) installed and configured with a profile (`databricks configure --profile <name>`)
- A Databricks cluster with access to the Unity Catalog volume `retail_assistant.retail.retail_volume`

## Cluster library versions

Install these as **PyPI** libraries on the cluster. If an older version of a library is already installed, **uninstall it first** — duplicate entries with different versions cause pip resolution failures.

| Library | Version | Type | Notes |
|---|---|---|---|
| `neo4j-agent-memory` | `0.0.1` | Wheel | Built from `maf` branch (Steps 1–3 below) |
| `neo4j` | `6.1.0` | PyPI | agent-memory requires `>=5.20.0` |
| `langgraph` | `1.0.8` | PyPI | Required by `langchain==1.2.10` (`>=1.0.8,<1.1.0`) |
| `langchain-core` | `>=1.2.0` | PyPI | Required by `langchain-openai` and `langchain` |
| `langchain-openai` | `1.1.2` | PyPI | Requires `openai>=2.20.0,<3.0.0` |
| `openai` | `2.21.0` | PyPI | Required by agent-memory `[openai]` extra and `langchain-openai` |
| `pydantic` | `2.12.5` | PyPI | |
| `pydantic-settings` | `2.13.0` | PyPI | |
| `databricks-agents` | `1.9.3` | PyPI | |
| `databricks-langchain` | `0.15.0` | PyPI | Requires `langchain>=1.0.0`, `openai>=1.99.9` |
| `neo4j-graphrag` | `1.13.0` | PyPI | |

### Version compatibility chain

The versions above are driven by `databricks-langchain==0.15.0`, which requires:

```
databricks-langchain>=0.15.0
  → langchain>=1.0.0 (latest: 1.2.10)
    → langchain-core>=1.2.10,<2.0.0
    → langgraph>=1.0.8,<1.1.0
  → openai>=1.99.9 (effectively openai 2.x)

langchain-openai==1.1.2
  → langchain-core>=1.2.0,<2.0.0
  → openai>=2.20.0,<3.0.0
```

All versions listed in the table are mutually compatible.

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

Then add each PyPI library from the table above (same **Install new** dialog, select **PyPI** as the source).

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
