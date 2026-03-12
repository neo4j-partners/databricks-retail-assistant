"""Prototype: Build GraphRAG layer using neo4j-graphrag-python SimpleKGPipeline.

Standalone script for dbx_rd/ prototyping. Runs on Databricks cluster via:
    ./upload.sh --all && ./submit.sh load_graphrag.py

Reads document text directly from Neo4j (loaded by step2_load_products.py),
so no dependency on the retail_agent data package.

Prerequisites:
    - step2_load_products.py has been run (KnowledgeArticle, SupportTicket,
      Review nodes exist in Neo4j)
    - neo4j-graphrag>=1.13.0 installed on the cluster
    - Databricks secrets set for Neo4j credentials
"""

import asyncio
import sys

import neo4j
from neo4j_graphrag.experimental.components.types import LexicalGraphConfig
from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline

from databricks_embedder import DatabricksEmbedder
from databricks_llm import DatabricksLLM
from deploy_config import CONFIG


# ---------------------------------------------------------------------------
# Neo4j credentials (same pattern as step3_load_graphrag.py)
# ---------------------------------------------------------------------------


def _get_neo4j_credentials() -> tuple[str, str]:
    """Get Neo4j URI and password from Databricks secrets via dbutils."""
    scope = CONFIG.secret_scope
    uri_key = CONFIG.neo4j_uri_secret
    password_key = CONFIG.neo4j_password_secret

    try:
        from pyspark.dbutils import DBUtils
        from pyspark.sql import SparkSession

        spark = SparkSession.builder.getOrCreate()
        dbutils = DBUtils(spark)
        uri = dbutils.secrets.get(scope, uri_key)
        password = dbutils.secrets.get(scope, password_key)
        if uri and password:
            print(f"  Credentials from dbutils secrets ({scope})")
            return uri, password
    except Exception:
        pass

    raise ValueError(
        f"Could not read Neo4j credentials from Databricks secrets "
        f"(scope={scope}, keys={uri_key}, {password_key})"
    )


# ---------------------------------------------------------------------------
# Fetch documents from Neo4j (loaded by step2)
# ---------------------------------------------------------------------------


def _fetch_documents(driver: neo4j.Driver) -> list[dict]:
    """Fetch document texts from Neo4j nodes created by step2_load_products.py.

    Returns a list of dicts with 'text' and 'metadata' keys, ready for
    SimpleKGPipeline.run_async().
    """
    documents = []

    # Knowledge articles
    records, _, _ = driver.execute_query(
        "MATCH (ka:KnowledgeArticle) "
        "RETURN ka.article_id AS id, ka.content AS text"
    )
    ka_count = 0
    for r in records:
        if r["text"] and r["text"].strip():
            documents.append({
                "text": r["text"],
                "metadata": {
                    "source_type": "KnowledgeArticle",
                    "source_id": r["id"],
                },
            })
            ka_count += 1
    print(f"  KnowledgeArticles: {ka_count}")

    # Support tickets — concatenate issue + resolution as one document
    records, _, _ = driver.execute_query(
        "MATCH (st:SupportTicket) "
        "RETURN st.ticket_id AS id, "
        "st.issue_description AS issue, st.resolution_text AS resolution"
    )
    ticket_count = 0
    for r in records:
        parts = []
        if r["issue"] and r["issue"].strip():
            parts.append(r["issue"])
        if r["resolution"] and r["resolution"].strip():
            parts.append(r["resolution"])
        if parts:
            documents.append({
                "text": "\n\n---\n\n".join(parts),
                "metadata": {
                    "source_type": "SupportTicket",
                    "source_id": r["id"],
                },
            })
            ticket_count += 1
    print(f"  SupportTickets: {ticket_count}")

    # Reviews
    records, _, _ = driver.execute_query(
        "MATCH (r:Review) RETURN r.review_id AS id, r.raw_text AS text"
    )
    review_count = 0
    for r in records:
        if r["text"] and r["text"].strip():
            documents.append({
                "text": r["text"],
                "metadata": {
                    "source_type": "Review",
                    "source_id": r["id"],
                },
            })
            review_count += 1
    print(f"  Reviews: {review_count}")

    return documents


# ---------------------------------------------------------------------------
# GraphSchema for entity extraction
# ---------------------------------------------------------------------------

SCHEMA = {
    "node_types": [
        {
            "label": "Feature",
            "description": "product feature or capability, 2-6 words",
        },
        {
            "label": "Symptom",
            "description": "product issue, defect, or problem, 2-6 words",
        },
        {
            "label": "Solution",
            "description": "fix, workaround, or recommendation, 2-6 words",
        },
    ],
    "relationship_types": [
        {"label": "HAS_FEATURE"},
        {"label": "HAS_SYMPTOM"},
        {"label": "HAS_SOLUTION"},
        {"label": "RELATED_TO"},
    ],
    "patterns": [
        ("Feature", "RELATED_TO", "Symptom"),
        ("Symptom", "HAS_SOLUTION", "Solution"),
        ("Feature", "RELATED_TO", "Solution"),
    ],
}


# ---------------------------------------------------------------------------
# Post-pipeline Step 1: Link chunks to existing document nodes
# ---------------------------------------------------------------------------


def _link_chunks_to_documents(driver: neo4j.Driver):
    """Create HAS_CHUNK relationships from existing doc nodes to library-created chunks.

    The library creates Document nodes with source_type and source_id properties
    (from document_metadata). This step bridges those to the pre-existing
    KnowledgeArticle, SupportTicket, and Review nodes created by step2.
    """
    for source_type, label, id_prop in [
        ("KnowledgeArticle", "KnowledgeArticle", "article_id"),
        ("SupportTicket", "SupportTicket", "ticket_id"),
        ("Review", "Review", "review_id"),
    ]:
        print(f"  Linking chunks to {label} nodes...")
        driver.execute_query(
            f"""
            MATCH (ch:Chunk)-[:FROM_DOCUMENT]->(d:Document {{source_type: $source_type}})
            MATCH (doc:{label} {{{id_prop}: d.source_id}})
            MERGE (doc)-[:HAS_CHUNK]->(ch)
            SET ch.source_type = $source_type
            """,
            source_type=source_type,
        )


# ---------------------------------------------------------------------------
# Post-pipeline Step 2: Create product-level entity shortcuts
# ---------------------------------------------------------------------------


def _create_product_shortcuts(driver: neo4j.Driver):
    """Create Product-level entity relationships by traversing the graph.

    Follows the same pattern as the current step3's _link_entities_to_products,
    but with the reversed FROM_CHUNK direction (entity->chunk).
    """
    for rel_type, entity_label in [
        ("HAS_FEATURE", "Feature"),
        ("HAS_SYMPTOM", "Symptom"),
        ("HAS_SOLUTION", "Solution"),
    ]:
        print(f"  Creating {rel_type} shortcuts...")
        driver.execute_query(f"""
            MATCH (p:Product)<-[:COVERS|ABOUT|REVIEWS]-(doc)
                  -[:HAS_CHUNK]->(ch)<-[:FROM_CHUNK]-(e:{entity_label})
            MERGE (p)-[:{rel_type}]->(e)
        """)


# ---------------------------------------------------------------------------
# Post-pipeline Step 3: Create indexes
# ---------------------------------------------------------------------------


def _create_indexes(driver: neo4j.Driver):
    """Create vector and fulltext indexes on Chunk nodes."""
    dims = CONFIG.embedding_dimensions

    print(f"  Creating vector index (chunk_embedding, {dims} dims)...")
    try:
        driver.execute_query("DROP INDEX chunk_embedding IF EXISTS")
        driver.execute_query(f"""
            CREATE VECTOR INDEX chunk_embedding
            FOR (ch:Chunk)
            ON (ch.embedding)
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: {dims},
                `vector.similarity_function`: 'cosine'
            }}}}
        """)
    except Exception as e:
        print(f"    Vector index note: {e}")

    print("  Creating fulltext index (chunkText)...")
    try:
        driver.execute_query("DROP INDEX chunkText IF EXISTS")
        driver.execute_query("""
            CREATE FULLTEXT INDEX chunkText
            FOR (ch:Chunk)
            ON EACH [ch.text]
            OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}}
        """)
    except Exception as e:
        print(f"    Fulltext index note: {e}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _print_counts(driver: neo4j.Driver):
    """Print node and relationship counts for verification."""
    queries = [
        ("Chunks", "MATCH (c:Chunk) RETURN count(c) AS count"),
        ("Documents", "MATCH (d:Document) RETURN count(d) AS count"),
        ("Features", "MATCH (f:Feature) RETURN count(f) AS count"),
        ("Symptoms", "MATCH (s:Symptom) RETURN count(s) AS count"),
        ("Solutions", "MATCH (sol:Solution) RETURN count(sol) AS count"),
        ("FROM_CHUNK rels", "MATCH ()-[r:FROM_CHUNK]->() RETURN count(r) AS count"),
        ("FROM_DOCUMENT rels", "MATCH ()-[r:FROM_DOCUMENT]->() RETURN count(r) AS count"),
        ("HAS_CHUNK rels", "MATCH ()-[r:HAS_CHUNK]->() RETURN count(r) AS count"),
        ("HAS_FEATURE rels", "MATCH ()-[r:HAS_FEATURE]->() RETURN count(r) AS count"),
        ("HAS_SYMPTOM rels", "MATCH ()-[r:HAS_SYMPTOM]->() RETURN count(r) AS count"),
        ("HAS_SOLUTION rels", "MATCH ()-[r:HAS_SOLUTION]->() RETURN count(r) AS count"),
        ("NEXT_CHUNK rels", "MATCH ()-[r:NEXT_CHUNK]->() RETURN count(r) AS count"),
    ]
    for label, cypher in queries:
        records, _, _ = driver.execute_query(cypher)
        print(f"  {label}: {records[0]['count']}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def run_pipeline() -> int:
    """Build GraphRAG layer using SimpleKGPipeline."""
    print("=" * 60)
    print("Phase 4a: GraphRAG Pipeline Prototype")
    print("=" * 60)

    # Neo4j connection
    print("\nGetting Neo4j credentials...")
    try:
        uri, password = _get_neo4j_credentials()
    except ValueError as e:
        print(f"  Error: {e}")
        return 1

    driver = neo4j.GraphDatabase.driver(uri, auth=("neo4j", password))
    try:
        driver.verify_connectivity()
        print("  Connected to Neo4j")

        # Fetch documents from Neo4j (loaded by step2)
        print("\nFetching documents from Neo4j...")
        documents = _fetch_documents(driver)
        print(f"  Total documents: {len(documents)}")

        if not documents:
            print("\n  No documents found. Has step2_load_products.py been run?")
            return 1

        # Initialize adapters
        print("\nInitializing adapters...")
        embedder = DatabricksEmbedder()
        llm = DatabricksLLM()
        print(f"  Embedder: {embedder.model}")
        print(f"  LLM: {llm.model_id}")

        # Configure pipeline
        print("\nConfiguring SimpleKGPipeline...")
        lexical_config = LexicalGraphConfig(chunk_id_property="chunk_id")

        pipeline = SimpleKGPipeline(
            llm=llm,
            driver=driver,
            embedder=embedder,
            schema=SCHEMA,
            from_pdf=False,
            lexical_graph_config=lexical_config,
            perform_entity_resolution=True,
            on_error="IGNORE",
        )
        print("  Pipeline created")

        # Process documents
        print(f"\nProcessing {len(documents)} documents through SimpleKGPipeline...")
        success = 0
        failed = 0

        for i, doc in enumerate(documents):
            try:
                await pipeline.run_async(
                    text=doc["text"],
                    document_metadata=doc["metadata"],
                )
                success += 1
            except Exception as e:
                failed += 1
                src = doc["metadata"]
                print(
                    f"  Error on {src['source_type']} {src['source_id']}: "
                    f"{type(e).__name__}: {e}"
                )

            if (i + 1) % 25 == 0 or (i + 1) == len(documents):
                print(
                    f"  Processed {i + 1}/{len(documents)} "
                    f"(success={success}, failed={failed})"
                )

        # Post-pipeline steps
        print("\nPost-pipeline Step 1: Link chunks to document nodes...")
        _link_chunks_to_documents(driver)

        print("\nPost-pipeline Step 2: Create product-level shortcuts...")
        _create_product_shortcuts(driver)

        print("\nPost-pipeline Step 3: Create indexes...")
        _create_indexes(driver)

        # Verification
        print("\nGraph counts:")
        _print_counts(driver)

        print(f"\n{'=' * 60}")
        print(f"Pipeline complete! {success} processed, {failed} failed.")
        print(f"{'=' * 60}")
        return 0

    finally:
        driver.close()


# ---------------------------------------------------------------------------
# Databricks event loop handling
# ---------------------------------------------------------------------------

# Databricks always has a running event loop (notebooks and job clusters).
# nest_asyncio patches it so asyncio.run() works inside the existing loop.
try:
    import nest_asyncio

    nest_asyncio.apply()
except ImportError:
    pass  # Not on Databricks — not needed

print(f"[load_graphrag] prototype, version=2026-03-11a")

if __name__ == "__main__":
    sys.exit(asyncio.run(run_pipeline()))
else:
    # Databricks Workspace: __name__ is not "__main__" when using the Run button
    asyncio.run(run_pipeline())
