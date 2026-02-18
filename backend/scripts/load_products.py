"""Load sample product data into Neo4j for the retail assistant demo."""

import asyncio

from neo4j import AsyncGraphDatabase

from backend.config import get_settings
from backend.scripts.product_catalog import BOUGHT_TOGETHER, CATEGORIES, PRODUCTS, SHARED_ATTRIBUTES


async def load_sample_data():
    """Load all sample data into Neo4j."""
    settings = get_settings()
    uri = settings.neo4j_uri
    user = settings.neo4j_username
    password = settings.neo4j_password.get_secret_value()

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

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

        print("Generating embeddings...")
        await _generate_embeddings(session)

    await driver.close()
    print("\nSample data loaded successfully!")
    print(f"  Products: {len(PRODUCTS)}")
    print(f"  Categories: {len(CATEGORIES)}")
    print(f"  Bought-together pairs: {len(BOUGHT_TOGETHER)}")


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
    # Create categories
    await session.run(
        """
        UNWIND $categories AS cat
        MERGE (c:Category {name: cat.name})
        SET c.description = cat.description
        """,
        {"categories": [{"name": k, "description": v} for k, v in CATEGORIES.items()]},
    )

    # Create brands from products
    await session.run(
        """
        MATCH (p:Product)
        WITH DISTINCT p.brand AS brand_name
        WHERE brand_name IS NOT NULL
        MERGE (b:Brand {name: brand_name})
        """
    )

    # Create relationships
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
    # Create Attribute nodes
    await session.run(
        """
        UNWIND $attrs AS attr
        MERGE (a:Attribute {name: attr.name, value: attr.value})
        """,
        {"attrs": [{"name": a[0], "value": a[1]} for a in SHARED_ATTRIBUTES]},
    )

    # Build product-to-attribute links from the Python-side attributes data
    # Map: attribute_name -> (product_attributes_key, attr_node_name)
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
    """Create vector index for product embeddings."""
    try:
        await session.run(
            """
            CREATE VECTOR INDEX product_embedding IF NOT EXISTS
            FOR (p:Product)
            ON (p.embedding)
            OPTIONS {indexConfig: {
                `vector.dimensions`: 1536,
                `vector.similarity_function`: 'cosine'
            }}
            """
        )
        print("  Vector index created (or already exists)")
    except Exception as e:
        print(f"  Vector index creation note: {e}")


async def _generate_embeddings(session):
    """Generate and store embeddings for products using OpenAI."""
    settings = get_settings()
    api_key = settings.openai_api_key or settings.azure_openai_api_key
    if not api_key:
        print("  No OpenAI API key configured — skipping embedding generation.")
        print("  Products will work with text search fallback.")
        return

    model = settings.azure_openai_embedding_deployment or "text-embedding-3-small"

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key.get_secret_value())

        # Build texts to embed
        texts = [f"{p.name}: {p.description}" for p in PRODUCTS]

        # Batch embed
        response = await client.embeddings.create(
            input=texts,
            model=model,
        )

        # Store embeddings on products
        for i, product in enumerate(PRODUCTS):
            embedding = response.data[i].embedding
            await session.run(
                """
                MATCH (p:Product {id: $product_id})
                SET p.embedding = $embedding
                """,
                {"product_id": product.id, "embedding": embedding},
            )

        print(f"  Generated embeddings for {len(PRODUCTS)} products")

    except ImportError:
        print("  openai package not installed — skipping embedding generation.")
        print("  Install with: pip install openai")
    except Exception as e:
        print(f"  Embedding generation failed: {e}")
        print("  Products will work with text search fallback.")


if __name__ == "__main__":
    asyncio.run(load_sample_data())
