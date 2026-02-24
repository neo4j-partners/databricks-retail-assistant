"""Build GraphRAG layer on top of existing product knowledge graph.

Run AFTER load_products.py. Adds Chunk nodes with embeddings,
extracts Feature/Symptom/Solution entities via LLM, and links
entities to chunks and products.

Databricks-only version. Gets Neo4j credentials from Databricks secrets.

Usage:
    uv run python -m dbx_agent.load_graphrag
"""

import asyncio
import json
import sys

from neo4j import AsyncGraphDatabase

from dbx_agent.data.product_knowledge import (
    KNOWLEDGE_ARTICLES,
    REVIEWS,
    SUPPORT_TICKETS,
)
from dbx_agent.src.deploy_config import CONFIG


# ---------------------------------------------------------------------------
# Entity extraction prompt
# ---------------------------------------------------------------------------

_ENTITY_EXTRACTION_PROMPT = """\
You are an entity extractor for a retail product knowledge base.

Given a text chunk, extract entities in these categories:
- Feature: A product technology, material, or capability (e.g., "React foam midsole", "Continental rubber outsole", "Dri-FIT moisture wicking")
- Symptom: A problem or issue (e.g., "outsole separation", "cushion responsiveness loss", "fabric pilling")
- Solution: A fix or recommendation (e.g., "replace every 300-500 miles", "use heel-lock lacing", "wash with vinegar")

Return ONLY a JSON object with three arrays. Use short canonical names (2-6 words). If a category has no entities, use an empty array.

Example 1:
Text: "The React foam midsole feels less responsive after 300+ miles. This cushion responsiveness loss is common across all foam technologies. Solution: Replace shoes every 300-500 miles. Rotating between two pairs extends life."
Output: {{"features": ["React foam midsole"], "symptoms": ["cushion responsiveness loss"], "solutions": ["replace every 300-500 miles", "rotate between two pairs"]}}

Example 2:
Text: "Customer reports blisters on both heels after every run in these shoes."
Output: {{"features": [], "symptoms": ["heel blisters"], "solutions": []}}

Example 3:
Text: "Advised customer to use heel-lock lacing technique and thicker cushioned socks. Customer reported improvement after one week."
Output: {{"features": ["heel-lock lacing"], "symptoms": [], "solutions": ["use heel-lock lacing technique", "wear thicker cushioned socks"]}}

Text: "{text}"
Output:"""


# ---------------------------------------------------------------------------
# Neo4j credentials (same pattern as load_products.py)
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
        f"(scope={scope}, keys={uri_key}, {password_key}). "
        f"Set them with: databricks secrets put-secret {scope} {uri_key}"
    )


# ---------------------------------------------------------------------------
# Stage 1 — Chunk
# ---------------------------------------------------------------------------


def _build_chunks() -> list[dict]:
    """Build chunk dicts from knowledge articles, tickets, and reviews."""
    chunks = []

    for ka in KNOWLEDGE_ARTICLES:
        chunk_id = f"{ka.article_id.lower()}-0"
        chunks.append({
            "chunk_id": chunk_id,
            "text": ka.content,
            "source_type": "KnowledgeArticle",
            "source_id": ka.article_id,
            "position": 0,
        })

    for t in SUPPORT_TICKETS:
        tid = t.ticket_id.lower()
        chunks.append({
            "chunk_id": f"{tid}-0",
            "text": t.issue_description,
            "source_type": "SupportTicket",
            "source_id": t.ticket_id,
            "position": 0,
        })
        chunks.append({
            "chunk_id": f"{tid}-1",
            "text": t.resolution_text,
            "source_type": "SupportTicket",
            "source_id": t.ticket_id,
            "position": 1,
        })

    for r in REVIEWS:
        chunk_id = f"{r.review_id.lower()}-0"
        chunks.append({
            "chunk_id": chunk_id,
            "text": r.raw_text,
            "source_type": "Review",
            "source_id": r.review_id,
            "position": 0,
        })

    return chunks


async def _create_chunks(session, chunks: list[dict]):
    """Create Chunk nodes and HAS_CHUNK / NEXT_CHUNK relationships."""
    # Create all Chunk nodes
    await session.run(
        """
        UNWIND $chunks AS c
        CREATE (ch:Chunk {
            chunk_id: c.chunk_id,
            text: c.text,
            source_type: c.source_type,
            source_id: c.source_id,
            position: c.position
        })
        """,
        {"chunks": chunks},
    )
    print(f"  Created {len(chunks)} Chunk nodes")

    # HAS_CHUNK from KnowledgeArticle
    await session.run(
        """
        MATCH (ka:KnowledgeArticle), (ch:Chunk {source_type: 'KnowledgeArticle'})
        WHERE ka.article_id = ch.source_id
        CREATE (ka)-[:HAS_CHUNK]->(ch)
        """
    )

    # HAS_CHUNK from SupportTicket
    await session.run(
        """
        MATCH (st:SupportTicket), (ch:Chunk {source_type: 'SupportTicket'})
        WHERE st.ticket_id = ch.source_id
        CREATE (st)-[:HAS_CHUNK]->(ch)
        """
    )

    # HAS_CHUNK from Review
    await session.run(
        """
        MATCH (r:Review), (ch:Chunk {source_type: 'Review'})
        WHERE r.review_id = ch.source_id
        CREATE (r)-[:HAS_CHUNK]->(ch)
        """
    )

    # NEXT_CHUNK for ticket chunk pairs (position 0 -> position 1)
    await session.run(
        """
        MATCH (c0:Chunk {source_type: 'SupportTicket', position: 0})
        MATCH (c1:Chunk {source_type: 'SupportTicket', position: 1})
        WHERE c0.source_id = c1.source_id
        CREATE (c0)-[:NEXT_CHUNK]->(c1)
        """
    )
    print("  Created HAS_CHUNK and NEXT_CHUNK relationships")


# ---------------------------------------------------------------------------
# Stage 2 — Embed
# ---------------------------------------------------------------------------


async def _embed_chunks(session, chunks: list[dict]):
    """Generate embeddings for chunks and create vector + fulltext indexes."""
    try:
        import mlflow.deployments
    except ImportError:
        print("  mlflow not available — skipping chunk embeddings.")
        return

    model = CONFIG.embedding_model
    dims = CONFIG.embedding_dimensions
    print(f"  Model: {model}")

    try:
        client = mlflow.deployments.get_deploy_client("databricks")
        texts = [c["text"] for c in chunks]

        # Batch in chunks of 100 to avoid request size limits
        batch_size = 100
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = client.predict(
                endpoint=model,
                inputs={"input": batch},
            )
            all_embeddings.extend(item["embedding"] for item in response["data"])
            print(f"  Embedded {min(i + batch_size, len(texts))}/{len(texts)} chunks")

        for i, chunk in enumerate(chunks):
            await session.run(
                """
                MATCH (ch:Chunk {chunk_id: $chunk_id})
                SET ch.embedding = $embedding
                """,
                {"chunk_id": chunk["chunk_id"], "embedding": all_embeddings[i]},
            )

        print(f"  Stored embeddings on {len(chunks)} chunks")

    except Exception as e:
        print(f"  Embedding generation failed: {e}")
        print("  Chunks will exist without embeddings.")
        return

    # Create vector index
    try:
        await session.run("DROP INDEX chunk_embedding IF EXISTS")
        await session.run(
            f"""
            CREATE VECTOR INDEX chunk_embedding
            FOR (ch:Chunk)
            ON (ch.embedding)
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: {dims},
                `vector.similarity_function`: 'cosine'
            }}}}
            """
        )
        print(f"  Vector index 'chunk_embedding' created — {dims} dimensions")
    except Exception as e:
        print(f"  Vector index creation note: {e}")

    # Create fulltext index with English analyzer
    try:
        await session.run("DROP INDEX chunkText IF EXISTS")
        await session.run(
            """
            CREATE FULLTEXT INDEX chunkText
            FOR (ch:Chunk)
            ON EACH [ch.text]
            OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}}
            """
        )
        print("  Fulltext index 'chunkText' created (English analyzer)")
    except Exception as e:
        print(f"  Fulltext index creation note: {e}")


# ---------------------------------------------------------------------------
# Stage 3 — Extract entities
# ---------------------------------------------------------------------------


def _parse_entity_response(raw: str) -> dict | None:
    """Parse LLM JSON response. Return None on failure."""
    text = raw.strip()
    # Handle markdown code block wrapping
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return None
        for key in ("features", "symptoms", "solutions"):
            if key not in parsed:
                parsed[key] = []
            if not isinstance(parsed[key], list):
                parsed[key] = []
            parsed[key] = [str(x).strip() for x in parsed[key] if x]
        return parsed
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


async def _extract_entities(session, chunks: list[dict]):
    """Extract Feature/Symptom/Solution entities from each chunk using LLM."""
    try:
        import mlflow.deployments
    except ImportError:
        print("  mlflow not available — skipping entity extraction.")
        return

    client = mlflow.deployments.get_deploy_client("databricks")
    llm_endpoint = "databricks-meta-llama-3-3-70b-instruct"

    extracted = 0
    skipped = 0

    for i, chunk in enumerate(chunks):
        # Escape braces in chunk text for the prompt template
        safe_text = chunk["text"].replace("{", "{{").replace("}", "}}")
        prompt = _ENTITY_EXTRACTION_PROMPT.format(text=safe_text)

        try:
            response = client.predict(
                endpoint=llm_endpoint,
                inputs={
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.0,
                },
            )
            raw_text = response["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  Warning: LLM call failed for {chunk['chunk_id']}: {e}")
            skipped += 1
            continue

        entities = _parse_entity_response(raw_text)
        if entities is None:
            print(f"  Warning: malformed JSON for {chunk['chunk_id']}, skipping")
            skipped += 1
            continue

        chunk_id = chunk["chunk_id"]

        if entities["features"]:
            await session.run(
                """
                UNWIND $names AS name
                MERGE (f:Feature {name: name})
                WITH f
                MATCH (ch:Chunk {chunk_id: $chunk_id})
                CREATE (ch)-[:MENTIONS_FEATURE]->(f)
                """,
                {"names": entities["features"], "chunk_id": chunk_id},
            )

        if entities["symptoms"]:
            await session.run(
                """
                UNWIND $names AS name
                MERGE (s:Symptom {name: name})
                WITH s
                MATCH (ch:Chunk {chunk_id: $chunk_id})
                CREATE (ch)-[:REPORTS_SYMPTOM]->(s)
                """,
                {"names": entities["symptoms"], "chunk_id": chunk_id},
            )

        if entities["solutions"]:
            await session.run(
                """
                UNWIND $names AS name
                MERGE (sol:Solution {name: name})
                WITH sol
                MATCH (ch:Chunk {chunk_id: $chunk_id})
                CREATE (ch)-[:PROVIDES_SOLUTION]->(sol)
                """,
                {"names": entities["solutions"], "chunk_id": chunk_id},
            )

        extracted += 1
        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{len(chunks)} chunks")

    print(f"  Entity extraction complete: {extracted} processed, {skipped} skipped")


# ---------------------------------------------------------------------------
# Stage 4 — Link entities to products
# ---------------------------------------------------------------------------


async def _link_entities_to_products(session):
    """Create Product-level entity relationships by graph traversal."""
    # HAS_FEATURE
    await session.run(
        """
        MATCH (p:Product)<-[:COVERS|ABOUT|REVIEWS]-(doc)-[:HAS_CHUNK]->(ch:Chunk)-[:MENTIONS_FEATURE]->(f:Feature)
        MERGE (p)-[:HAS_FEATURE]->(f)
        """
    )
    print("  Created Product -[HAS_FEATURE]-> Feature")

    # HAS_SYMPTOM
    await session.run(
        """
        MATCH (p:Product)<-[:COVERS|ABOUT|REVIEWS]-(doc)-[:HAS_CHUNK]->(ch:Chunk)-[:REPORTS_SYMPTOM]->(s:Symptom)
        MERGE (p)-[:HAS_SYMPTOM]->(s)
        """
    )
    print("  Created Product -[HAS_SYMPTOM]-> Symptom")

    # HAS_SOLUTION
    await session.run(
        """
        MATCH (p:Product)<-[:COVERS|ABOUT|REVIEWS]-(doc)-[:HAS_CHUNK]->(ch:Chunk)-[:PROVIDES_SOLUTION]->(sol:Solution)
        MERGE (p)-[:HAS_SOLUTION]->(sol)
        """
    )
    print("  Created Product -[HAS_SOLUTION]-> Solution")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def load_graphrag() -> int:
    """Build GraphRAG layer: chunk, embed, extract entities, link to products."""
    print("=== GraphRAG Pipeline ===")
    print("Getting Neo4j credentials from Databricks secrets...")
    try:
        uri, password = _get_neo4j_credentials()
    except ValueError as e:
        print(f"  Error: {e}")
        return 1

    driver = AsyncGraphDatabase.driver(uri, auth=("neo4j", password))

    chunks = _build_chunks()

    async with driver.session() as session:
        print(f"\nStage 1 — Chunk ({len(chunks)} chunks)...")
        await _create_chunks(session, chunks)

        print("\nStage 2 — Embed...")
        await _embed_chunks(session, chunks)

        print("\nStage 3 — Extract entities...")
        await _extract_entities(session, chunks)

        print("\nStage 4 — Link entities to products...")
        await _link_entities_to_products(session)

    await driver.close()

    ka_chunks = len(KNOWLEDGE_ARTICLES)
    ticket_chunks = len(SUPPORT_TICKETS) * 2
    review_chunks = len(REVIEWS)

    print(f"\nGraphRAG pipeline complete!")
    print(f"  Chunks: {len(chunks)}")
    print(f"    KnowledgeArticle: {ka_chunks}")
    print(f"    SupportTicket: {ticket_chunks} (2 per ticket)")
    print(f"    Review: {review_chunks}")
    return 0


# ---------------------------------------------------------------------------
# Module boilerplate (same pattern as load_products.py)
# ---------------------------------------------------------------------------

# Databricks always has a running event loop (notebooks and job clusters).
# nest_asyncio patches it so asyncio.run() works inside the existing loop.
try:
    import nest_asyncio

    nest_asyncio.apply()
except ImportError:
    pass  # Not on Databricks — not needed

print(f"[load_graphrag] __name__={__name__}, version=2025-02-23a")

if __name__ == "__main__":
    sys.exit(asyncio.run(load_graphrag()))
else:
    # Databricks Workspace: __name__ is not "__main__" when using the Run button
    asyncio.run(load_graphrag())
