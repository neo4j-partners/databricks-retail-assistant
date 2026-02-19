"""Load sample product data into Neo4j for the retail assistant demo.

Databricks-only version. Gets Neo4j credentials from Databricks secrets
using the same scope and keys as the deployed agent (see config.py).

Usage:
    uv run python -m dbx_agent.load_products

Prerequisites:
    1. Databricks CLI configured (databricks auth login)
    2. Databricks secrets set:
         databricks secrets put-secret retail-agent-secrets neo4j-uri
         databricks secrets put-secret retail-agent-secrets neo4j-password
"""

import asyncio
import sys

from neo4j import AsyncGraphDatabase

from backend.scripts.product_catalog import (
    BOUGHT_TOGETHER,
    CATEGORIES,
    PRODUCTS,
    SHARED_ATTRIBUTES,
)
from dbx_agent.config import CONFIG


def _get_neo4j_credentials() -> tuple[str, str]:
    """Get Neo4j URI and password from Databricks secrets.

    Tries dbutils (notebook), then WorkspaceClient (CLI/jobs).
    """
    scope = CONFIG.secret_scope
    uri_key = CONFIG.neo4j_uri_secret
    password_key = CONFIG.neo4j_password_secret

    # Method 1: dbutils (Databricks notebook)
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

    # Method 2: WorkspaceClient (CLI)
    try:
        import base64

        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        uri = base64.b64decode(w.secrets.get_secret(scope, uri_key).value).decode("utf-8")
        password = base64.b64decode(w.secrets.get_secret(scope, password_key).value).decode("utf-8")
        if uri and password:
            print(f"  Credentials from WorkspaceClient secrets ({scope})")
            return uri, password
    except Exception:
        pass

    raise ValueError(
        f"Could not read Neo4j credentials from Databricks secrets "
        f"(scope={scope}, keys={uri_key}, {password_key}). "
        f"Set them with: databricks secrets put-secret {scope} {uri_key}"
    )


async def load_sample_data() -> int:
    """Load all sample data into Neo4j."""
    print("Getting Neo4j credentials from Databricks secrets...")
    try:
        uri, password = _get_neo4j_credentials()
    except ValueError as e:
        print(f"  Error: {e}")
        return 1

    driver = AsyncGraphDatabase.driver(uri, auth=("neo4j", password))

    async with driver.session() as session:
        print("Clearing existing data...")
        await _clear_database(session)

        print("Creating products...")
        await _create_products(session)

        print("Creating categories and brands...")
        await _create_categories_and_brands(session)

        print("Creating similarity relationships...")
        await _create_similarity_relationships(session)

        print("Creating bought-together relationships...")
        await _create_bought_together(session)

        print("Creating attribute nodes and relationships...")
        await _create_attributes(session)

        print("Creating vector index...")
        await _create_vector_index(session)

        print("Dropping stale agent-memory indexes...")
        await _drop_stale_memory_indexes(session)

        print("Generating product embeddings...")
        await _generate_embeddings(session)

    await driver.close()
    print(f"\nSample data loaded successfully!")
    print(f"  Products: {len(PRODUCTS)}")
    print(f"  Categories: {len(CATEGORIES)}")
    print(f"  Bought-together pairs: {len(BOUGHT_TOGETHER)}")
    return 0


async def _clear_database(session):
    """Delete all nodes and relationships."""
    await session.run("MATCH (n) DETACH DELETE n")


async def _create_products(session):
    """Create Product nodes with all properties."""
    await session.run(
        """
        UNWIND $products AS product
        MERGE (p:Product {id: product.id})
        SET p.name = product.name,
            p.description = product.description,
            p.price = product.price,
            p.category = product.category,
            p.brand = product.brand,
            p.in_stock = product.in_stock,
            p.inventory = product.inventory,
            p.popularity = product.popularity,
            p.style = product.style,
            p.image_url = product.image_url
        """,
        {"products": [p.model_dump() for p in PRODUCTS]},
    )


async def _create_categories_and_brands(session):
    """Create Category and Brand nodes with relationships."""
    await session.run(
        """
        UNWIND $categories AS cat
        MERGE (c:Category {name: cat.name})
        SET c.description = cat.description
        """,
        {"categories": [{"name": k, "description": v} for k, v in CATEGORIES.items()]},
    )

    await session.run(
        """
        MATCH (p:Product)
        WITH DISTINCT p.brand AS brand_name
        WHERE brand_name IS NOT NULL
        MERGE (b:Brand {name: brand_name})
        """
    )

    await session.run(
        """
        MATCH (p:Product), (c:Category {name: p.category})
        MERGE (p)-[:IN_CATEGORY]->(c)
        """
    )

    await session.run(
        """
        MATCH (p:Product), (b:Brand {name: p.brand})
        MERGE (p)-[:MADE_BY]->(b)
        """
    )


async def _create_similarity_relationships(session):
    """Create SIMILAR_TO relationships between products in the same category."""
    await session.run(
        """
        MATCH (p1:Product)-[:IN_CATEGORY]->(c)<-[:IN_CATEGORY]-(p2:Product)
        WHERE p1 <> p2
        MERGE (p1)-[:SIMILAR_TO]-(p2)
        """
    )


async def _create_bought_together(session):
    """Create BOUGHT_TOGETHER relationships."""
    await session.run(
        """
        UNWIND $pairs AS pair
        MATCH (p1:Product {id: pair.id1}), (p2:Product {id: pair.id2})
        MERGE (p1)-[r:BOUGHT_TOGETHER]-(p2)
        SET r.frequency = pair.frequency,
            r.confidence = pair.confidence
        """,
        {
            "pairs": [
                {"id1": p[0], "id2": p[1], "frequency": p[2], "confidence": p[3]}
                for p in BOUGHT_TOGETHER
            ]
        },
    )


async def _create_attributes(session):
    """Create Attribute nodes and HAS_ATTRIBUTE relationships."""
    await session.run(
        """
        UNWIND $attrs AS attr
        MERGE (a:Attribute {name: attr.name, value: attr.value})
        """,
        {"attrs": [{"name": a[0], "value": a[1]} for a in SHARED_ATTRIBUTES]},
    )

    attr_mappings = [
        ("cushion", "Cushion Level"),
        ("surface", "Surface"),
        ("occasion", "Occasion"),
        ("fit", "Fit"),
        ("material", "Material"),
    ]

    links = []
    for product in PRODUCTS:
        for attr_key, attr_name in attr_mappings:
            if attr_key in product.attributes:
                links.append({
                    "product_id": product.id,
                    "attr_name": attr_name,
                    "attr_value": product.attributes[attr_key],
                })

    await session.run(
        """
        UNWIND $links AS link
        MATCH (p:Product {id: link.product_id})
        MATCH (a:Attribute {name: link.attr_name, value: link.attr_value})
        MERGE (p)-[:HAS_ATTRIBUTE]->(a)
        """,
        {"links": links},
    )


async def _create_vector_index(session):
    """Create vector index for product embeddings.

    Drops and recreates the index to ensure dimensions match
    CONFIG.embedding_dimensions (e.g. 1024 for Databricks BGE).
    A stale index with wrong dimensions (e.g. 1536 from OpenAI) will
    silently fail every vector query.
    """
    dims = CONFIG.embedding_dimensions

    try:
        await session.run("DROP INDEX product_embedding IF EXISTS")
        await session.run(
            f"""
            CREATE VECTOR INDEX product_embedding
            FOR (p:Product)
            ON (p.embedding)
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: {dims},
                `vector.similarity_function`: 'cosine'
            }}}}
            """
        )
        print(f"  Vector index created — {dims} dimensions")
    except Exception as e:
        print(f"  Vector index creation note: {e}")


async def _drop_stale_memory_indexes(session):
    """Drop agent-memory vector indexes so they can be recreated at the correct size.

    The agent-memory library creates vector indexes during MemoryClient.connect():
        message_embedding_idx, entity_embedding_idx, preference_embedding_idx,
        fact_embedding_idx, task_embedding_idx

    If embedding dimensions changed (e.g., 1536 OpenAI → 1024 Databricks BGE),
    these must be dropped first. Since _clear_database() already deleted all
    nodes, we drop ALL non-product vector indexes so connect() recreates them
    at the correct size.
    """
    # Known agent-memory indexes (from schema.py setup_vector_indexes)
    memory_indexes = [
        "message_embedding_idx",
        "entity_embedding_idx",
        "preference_embedding_idx",
        "fact_embedding_idx",
        "task_embedding_idx",
    ]
    try:
        dropped = 0
        for idx_name in memory_indexes:
            await session.run(f"DROP INDEX {idx_name} IF EXISTS")
            dropped += 1
        print(f"  Dropped {dropped} agent-memory vector indexes")
    except Exception as e:
        print(f"  Memory index cleanup note: {e}")


async def _generate_embeddings(session):
    """Generate and store product embeddings using Databricks Foundation Model API."""
    try:
        import mlflow.deployments
    except ImportError:
        print("  mlflow not available — skipping embedding generation.")
        print("  Products will work with text search fallback.")
        return

    model = CONFIG.embedding_model
    print(f"  Model: {model}")

    try:
        client = mlflow.deployments.get_deploy_client("databricks")
        texts = [f"{p.name}: {p.description}" for p in PRODUCTS]

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
            print(f"  Embedded {min(i + batch_size, len(texts))}/{len(texts)} products")

        for i, product in enumerate(PRODUCTS):
            await session.run(
                """
                MATCH (p:Product {id: $product_id})
                SET p.embedding = $embedding
                """,
                {"product_id": product.id, "embedding": all_embeddings[i]},
            )

        print(f"  Generated embeddings for {len(PRODUCTS)} products")

    except Exception as e:
        print(f"  Embedding generation failed: {e}")
        print("  Products will work with text search fallback.")


# Databricks always has a running event loop (notebooks and job clusters).
# nest_asyncio (pre-installed on Databricks since runtime 10.4) patches it
# so asyncio.run() works inside the existing loop.
try:
    import nest_asyncio

    nest_asyncio.apply()
except ImportError:
    pass  # Not on Databricks — not needed

print(f"[load_products] __name__={__name__}, version=2025-02-18a")

if __name__ == "__main__":
    sys.exit(asyncio.run(load_sample_data()))
else:
    # Databricks Workspace: __name__ is not "__main__" when using the Run button
    asyncio.run(load_sample_data())
