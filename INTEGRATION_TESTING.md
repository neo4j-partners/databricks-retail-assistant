# Integration Testing

This document lists every test that must run against a real Databricks workspace and Neo4j database before a deployment of `databricks-neo4j-retail` is declared healthy. Each section is a checklist that an operator ticks off. Run sections in order; later sections assume earlier ones have passed.

The pipeline has six real steps plus one stub. Step 7, `step7_deploy_supervisor.py`, is currently a placeholder. It must print a `STUB` banner and exit 0 without deploying anything.

## 1. Local Prerequisites

These checks run on the developer machine before anything is submitted to Databricks.

- [x] `python --version` reports 3.12 or newer.
- [x] `uv --version` succeeds.
- [x] `databricks --version` succeeds. The CLI profile in `DATABRICKS_PROFILE` resolves: `databricks current-user me --profile $DATABRICKS_PROFILE`.
- [x] `../databricks-job-runner` exists as a sibling checkout.
- [x] `.env` is present and contains `NEO4J_URI`, `NEO4J_PASSWORD`, `DATABRICKS_PROFILE`, `DATABRICKS_COMPUTE_MODE`, `DATABRICKS_CLUSTER_ID`, `DATABRICKS_WORKSPACE_DIR`, `DATABRICKS_VOLUME_PATH`.
- [x] `uv sync` completes with no errors.
- [x] `uv run python -m py_compile` succeeds for every step entry point listed in the README "Local Validation" section, including `step7_deploy_supervisor.py`.

## 2. Workspace Prerequisites

- [x] Unity Catalog catalog `retail_assistant`, schema `retail`, and volume `retail_volume` exist.
- [x] The cluster referenced by `DATABRICKS_CLUSTER_ID` is in the `RUNNING` state.
- [x] The cluster has a Neo4j Spark Connector library compatible with the cluster runtime installed. Verified on Spark 4 / Scala 2.13 with `org.neo4j:neo4j-connector-apache-spark_2.13:5.3.10_for_spark_3`.
- [x] The cluster access mode is `Dedicated`. Shared mode does not work with the Neo4j Spark Connector.
- [x] Model Serving has access to the LLM endpoint `databricks-claude-sonnet-4-6`. Confirm via the Databricks UI or a direct invocation.
- [x] Model Serving has access to the embedding endpoint `databricks-bge-large-en`. Confirm via the Databricks UI or a direct invocation.
- [x] The Neo4j database referenced by `NEO4J_URI` is reachable from the cluster.

## 3. Secrets Setup

- [x] `./retail_agent/scripts/setup_databricks_secrets.sh --profile $DATABRICKS_PROFILE` exits 0.
- [x] `databricks secrets list-scopes --profile $DATABRICKS_PROFILE` includes `retail-agent-secrets`.
- [x] `databricks secrets list-secrets retail-agent-secrets --profile $DATABRICKS_PROFILE` lists keys `neo4j-uri` and `neo4j-password`.

## 4. Runner Validation

- [x] `uv run python -m cli validate` exits 0. The output reports the cluster as reachable, the workspace path as writable, and the uploaded jobs as visible.
- [x] Remote execution smoke test: `uv run python -m cli submit test_hello.py` succeeds. The job log prints the hello banner.

## 5. Upload Artifacts

- [x] `uv run python -m cli upload --all` uploads every wrapper in `jobs/` to `DATABRICKS_WORKSPACE_DIR`. The list includes `run_retail_agent_step7_deploy_supervisor.py`.
- [x] `uv run python -m cli upload --wheel` builds and uploads the current `retail_agent` wheel to `DATABRICKS_VOLUME_PATH/wheels/`.
- [x] The wheel filename in the volume matches the version in `pyproject.toml`.
- [x] Listing `DATABRICKS_WORKSPACE_DIR` from the workspace UI shows seven wrapper scripts.

## 6. Step 2: Load Product And Source Knowledge Graph

Run: `uv run python -m cli submit run_retail_agent_step2_load_products.py`

- [x] Job exits with status `SUCCESS`.
- [x] Neo4j: `MATCH (p:Product) RETURN count(p)` returns the expected count for the configured catalog. The expanded catalog produces 570 products.
- [x] Neo4j: `MATCH (c:Category) RETURN count(c)` returns a non-zero count.
- [x] Neo4j: `MATCH (b:Brand) RETURN count(b)` returns a non-zero count.
- [x] Neo4j: `MATCH (a:Attribute) RETURN count(a) > 0`.
- [x] Neo4j: relationships `IN_CATEGORY`, `MADE_BY`, `HAS_ATTRIBUTE`, `SIMILAR_TO`, `BOUGHT_TOGETHER` all exist with non-zero counts.
- [x] Neo4j: source nodes `KnowledgeArticle`, `SupportTicket`, and `Review` are present.
- [x] Neo4j: product vector index exists. Verify with `SHOW INDEXES YIELD name, type WHERE type = 'VECTOR'`.
- [x] Neo4j: agent memory indexes exist for the memory labels initialized by the current runtime: `Message`, `Entity`, `Preference`, and `Fact`. `Task` indexes are not created by the current Step 2 flow.

## 7. Step 3: Build GraphRAG Layer

Run: `uv run python -m cli submit run_retail_agent_step3_load_graphrag.py`

- [x] Job exits with status `SUCCESS`.
- [x] Job log reports the number of documents processed. The verified flow produces around 252.
- [x] Neo4j: `MATCH (c:Chunk) RETURN count(c) > 0`.
- [x] Neo4j: every `Chunk` has a non-null `chunk_id`. Verify with `MATCH (c:Chunk) WHERE c.chunk_id IS NULL RETURN count(c)` returning 0.
- [x] Neo4j: extracted entity nodes `Feature`, `Symptom`, and `Solution` exist with non-zero counts.
- [x] Neo4j: relationships `HAS_CHUNK`, `FROM_DOCUMENT`, `MENTIONS_FEATURE`, `REPORTS_SYMPTOM`, `PROVIDES_SOLUTION` exist with non-zero counts.
- [x] Neo4j: vector index `chunk_embedding` exists.
- [x] Neo4j: fulltext index `chunkText` exists.
- [x] Neo4j: entities link back to products via the expected shortcut relationships.

## 8. Step 1: Deploy The Agent

Run: `uv run python -m cli submit run_retail_agent_step1_deploy_agent.py`

- [x] Job exits with status `SUCCESS`.
- [x] Unity Catalog: `retail_assistant.retail.retail_agent_v3` has a new model version registered.
- [x] Model Serving: endpoint `agents_retail_assistant-retail-retail_agent_v3` is in the `READY` state.
- [x] Model Serving: the endpoint's served model points at the new version registered in this run.
- [x] Model Serving: the new version is the active traffic target. The job log must confirm this. Do not rely on `READY` alone.
- [x] The endpoint's environment variables include the `{{secrets/retail-agent-secrets/neo4j-uri}}` and `{{secrets/retail-agent-secrets/neo4j-password}}` references.

## 9. Step 4: Verify Endpoint, Products, And Memory

Run: `uv run python -m cli submit run_retail_agent_step4_demo_agent.py`

- [x] Job exits with status `SUCCESS`. The verified flow shows 9 passed, 0 failed.
- [x] Diagnostics tool reports Neo4j connectivity, an initialized `MemoryClient`, and a running persistent event loop.
- [x] Product search returns at least one hit for the test query.
- [x] Product detail lookup for a known product ID returns the correct product fields.
- [x] Related-product lookup returns at least one related product for the test product ID.
- [x] Short-term memory: a session-scoped `remember` followed by `recall` returns the stored value.
- [x] Long-term memory: a user preference stored on one turn is retrievable on a subsequent turn within the same user scope.
- [x] Negative test: submit with a deliberately broken endpoint name and confirm the job exits non-zero before memory checks run.

## 10. Step 5: Demonstrate GraphRAG Retrievers

Run: `uv run python -m cli submit run_retail_agent_step5_demo_retrievers.py`

- [x] Job exits with status `SUCCESS`.
- [x] Log shows results from `VectorRetriever`, `VectorCypherRetriever`, `HybridCypherRetriever`, and `Text2CypherRetriever`.
- [x] Each retriever returns at least one chunk for the seeded test query.
- [x] `Text2CypherRetriever` produces syntactically valid Cypher and a non-empty result.

## 11. Step 6: Verify Knowledge Tools Through The Endpoint

Run: `uv run python -m cli submit run_retail_agent_step6_check_knowledge.py`

- [x] Job exits with status `SUCCESS`. The verified flow shows 4 passed, 0 failed.
- [x] Troubleshooting query returns a coherent answer that cites symptoms and solutions from the GraphRAG layer.
- [x] Brand-specific hybrid search returns chunks scoped to the requested brand.
- [x] Product issue diagnosis returns a structured response that includes at least one solution.
- [x] Cross-product knowledge comparison returns content from at least two distinct products.
- [x] Negative test: submit with a deliberately broken endpoint name and confirm the job exits non-zero.

## 12. Step 7: Supervisor Stub

Run: `uv run python -m cli submit run_retail_agent_step7_deploy_supervisor.py`

- [x] Job exits with status `SUCCESS`.
- [x] Job log contains the literal string `STUB: step7_deploy_supervisor.py is a placeholder.`.
- [x] No new Model Serving endpoint named `retail_supervisor_v1` is created.
- [x] No new Unity Catalog model is registered for the supervisor.

## 13. End-To-End Smoke

Run after every individual section above has passed.

- [x] Run steps 2, 3, 1, 4, 5, 6, 7 in order from a clean workspace state. Every job exits `SUCCESS`.
- [x] The KG endpoint answers a product question, a recommendation question, a memory question, and a troubleshooting question inside one continuous chat session.
- [x] Logs from each step are retrievable via `uv run python -m cli logs <run-id>`.

## 14. Cleanup (Optional)

Use this section when tearing down a test environment.

- [ ] `agents.delete_deployment` removes the KG agent endpoint.
- [ ] `databricks unity-catalog models delete retail_assistant.retail.retail_agent_v3 --profile $DATABRICKS_PROFILE` removes the registered model.
- [ ] Neo4j: `MATCH (n) DETACH DELETE n` clears the database. Run only when the database is dedicated to this test.
- [ ] `databricks secrets delete-scope retail-agent-secrets --profile $DATABRICKS_PROFILE` removes the secret scope.
