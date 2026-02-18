# Proposal: Expand Retail Assistant with Databricks Lakehouse for Transaction Analytics

## Problem Statement

The current retail assistant demo uses Neo4j as its sole data backend. Neo4j stores 16 sample products, categories, brands, attributes, bought-together relationships, and the agent memory system (conversations, preferences, entities, reasoning traces). This is effective for demonstrating graph-powered recommendations and agent memory, but it misses a critical dimension of real retail systems: **high-volume transactional time-series data**.

Real retailers generate millions of purchase transactions per day. These transactions power demand forecasting, seasonal trend analysis, customer lifetime value calculations, basket analysis at scale, and inventory replenishment decisions. This data is inherently tabular and time-indexed — exactly the workload where a lakehouse with columnar storage and SQL analytics excels, and where a graph database is the wrong tool.

The aircraft digital twin workshop at `/Users/ryanknight/projects/aws-databricks-neo4j-lab` demonstrates this dual-database pattern effectively: Neo4j stores the richly connected topology (aircraft, systems, components, maintenance events, flights, airports) while Databricks stores the high-volume time-series sensor telemetry (345,600+ hourly readings). Each system handles the workload it was designed for, and a multi-agent architecture routes queries to the appropriate backend.

This proposal extends the retail assistant with the same pattern: Neo4j continues to own the product graph and agent memory, while Databricks Lakehouse stores the transaction history that enables time-series analytics the AI agent can query through natural language.

## Proposed Solution

### Dual-Database Architecture

```
                     Retail AI Assistant (LangGraph)
                              |
              ┌───────────────┼───────────────┐
              |               |               |
        Neo4j Aura      Databricks       Agent Memory
        (Graph DB)      (Lakehouse)       (Neo4j)
              |               |               |
     ┌────────┤         ┌────┤          ┌─────┤
     |        |         |    |          |     |
  Products  Graph    Trans- Store    Short  Long
  Brands    Rels     actions Meta    Term   Term
  Categories         Reviews         Conv   Prefs
  Attributes         Sessions        Hist   Entities
  Cart               Inventory              Reasoning
                     Snapshots              Traces
```

**Neo4j** continues to own:
- Product catalog with embeddings (16 → 500+ products)
- Category, Brand, and Attribute graph topology
- SIMILAR_TO, BOUGHT_TOGETHER, IN_CATEGORY, MADE_BY, HAS_ATTRIBUTE relationships
- Shopping cart state per session
- All three tiers of agent memory (short-term, long-term, reasoning)

**Databricks Lakehouse** (Delta Lake) stores:
- Purchase transactions (500,000+ records over 2 years)
- Customer sessions and browsing events
- Product reviews with ratings and timestamps
- Inventory snapshots over time (daily stock levels)
- Store/channel metadata

The **overlap** between the two systems is intentional and minimal: both store product IDs and basic product metadata (name, category, brand, price). This allows each system to execute queries independently without cross-database joins at query time. The product ID is the shared foreign key.

### What This Enables for the AI Agent

With the lakehouse integration, the agent gains new capabilities:

1. **"What's trending this month?"** — SQL aggregation over recent transactions, grouped by category or brand, compared to previous periods.
2. **"How has demand for running shoes changed over the past year?"** — Time-series trend analysis with rolling averages and seasonal decomposition.
3. **"What do customers who bought Nike Pegasus 40 typically buy next?"** — Large-scale sequential basket analysis across 500K transactions (complements the small static BOUGHT_TOGETHER graph in Neo4j).
4. **"What's the average rating for products in this category?"** — Review aggregation with temporal filtering.
5. **"Should I buy this now or wait?"** — Price and availability trend analysis from inventory snapshots.
6. **"What are the best-reviewed running shoes under $150?"** — Join reviews with product filters, aggregate ratings.

These queries involve scanning thousands to hundreds of thousands of rows with aggregations, window functions, and temporal filters — exactly what a lakehouse is optimized for and what Neo4j is not.

## Data Generation: `generate_transactions.py`

Following the pattern established by `generate_removal_data.py` in the aircraft workshop, this script generates a large-scale synthetic retail transaction dataset that maintains referential integrity with the existing Neo4j product catalog.

### Design Principles (Matching the Aircraft Pattern)

The aircraft `generate_removal_data.py` establishes several patterns this script follows:

1. **Read existing data for referential integrity** — The aircraft script reads `nodes_aircraft.csv` and `nodes_components.csv` to get valid IDs. The retail script reads the `PRODUCTS` list from `load_products.py` to get valid product IDs, prices, categories, and brands.

2. **Weighted distributions for realism** — The aircraft script uses weighted category selection (20% bearing wear, 18% fuel issues, etc.) and priority distributions (15/35/35/15% for CRITICAL/HIGH/MEDIUM/LOW). The retail script uses weighted distributions for purchase frequency by category, time-of-day patterns, seasonal multipliers, and customer segment behaviors.

3. **Derived fields with realistic correlations** — The aircraft script correlates priority to cost multiplier and scheduled maintenance probability. The retail script correlates customer segment to basket size, discount sensitivity, brand affinity, and return probability.

4. **CSV output with Neo4j-compatible headers** — The aircraft script outputs `:ID(RemovalEvent)` headers for direct Neo4j import. The retail script outputs standard CSV for Databricks Delta Lake ingestion, with product IDs matching the Neo4j catalog.

5. **Scale** — The aircraft script generates 500,000 records spanning 5 years. The retail script generates 500,000 transactions spanning 2 years (Jan 2023 – Dec 2024), plus supporting dimension tables.

### Generated Tables

#### `transactions.csv` (500,000 rows)

The core fact table. Each row is a single line item in a purchase.

| Column | Type | Description |
|--------|------|-------------|
| `transaction_id` | string | `TXN{YYMMDD}{sequence:06d}` |
| `order_id` | string | `ORD{YYMMDD}{sequence:06d}` (groups line items into orders) |
| `customer_id` | string | `CUST{:05d}` (5,000 unique customers) |
| `product_id` | string | Matches Neo4j Product.id (e.g., `nike-pegasus-40`) |
| `product_name` | string | Denormalized for lakehouse self-containment |
| `category` | string | Denormalized |
| `brand` | string | Denormalized |
| `quantity` | int | 1–5, weighted toward 1 |
| `unit_price` | float | Base price from product catalog |
| `discount_pct` | float | 0–30%, varies by season and customer segment |
| `total_price` | float | `quantity * unit_price * (1 - discount_pct)` |
| `purchase_date` | timestamp | Uniformly distributed over 2 years with seasonal weighting |
| `purchase_hour` | int | 0–23, weighted toward business hours and evening peaks |
| `day_of_week` | string | Derived from date |
| `channel` | string | `online` / `in_store` / `mobile_app` (60/25/15%) |
| `store_id` | string | `STORE{:03d}` (20 stores), NULL for online |
| `payment_method` | string | `credit_card` / `debit_card` / `paypal` / `apple_pay` |
| `returned` | boolean | 5–15% depending on category |
| `return_date` | timestamp | 1–30 days after purchase, NULL if not returned |
| `return_reason` | string | `wrong_size` / `defective` / `changed_mind` / `not_as_described`, NULL if not returned |

#### `customers.csv` (5,000 rows)

Customer dimension table with segments that drive purchasing behavior.

| Column | Type | Description |
|--------|------|-------------|
| `customer_id` | string | `CUST{:05d}` |
| `segment` | string | `loyal` / `occasional` / `new` / `bargain_hunter` (20/35/25/20%) |
| `signup_date` | date | 2020–2024 |
| `preferred_channel` | string | `online` / `in_store` / `mobile_app` |
| `city` | string | 30 US cities |
| `state` | string | State abbreviation |
| `age_group` | string | `18-24` / `25-34` / `35-44` / `45-54` / `55+` |

#### `reviews.csv` (50,000 rows)

Product reviews linked to transactions.

| Column | Type | Description |
|--------|------|-------------|
| `review_id` | string | `REV{:06d}` |
| `transaction_id` | string | Links to transactions table |
| `customer_id` | string | Links to customers table |
| `product_id` | string | Matches Neo4j Product.id |
| `rating` | int | 1–5, weighted distribution (mean ~4.0) |
| `review_date` | timestamp | 1–60 days after purchase |
| `verified_purchase` | boolean | Always true (linked to transaction) |

#### `inventory_snapshots.csv` (100,000+ rows)

Daily inventory levels per product over 2 years (~16 products x 730 days, expandable with more products).

| Column | Type | Description |
|--------|------|-------------|
| `snapshot_date` | date | Daily from 2023-01-01 to 2024-12-31 |
| `product_id` | string | Matches Neo4j Product.id |
| `stock_level` | int | Opening stock for the day |
| `units_sold` | int | Derived from transactions for that day |
| `units_received` | int | Replenishment (periodic, varies by product) |
| `stock_status` | string | `in_stock` / `low_stock` / `out_of_stock` |

#### `stores.csv` (20 rows)

Store dimension table.

| Column | Type | Description |
|--------|------|-------------|
| `store_id` | string | `STORE{:03d}` |
| `store_name` | string | City-based name |
| `city` | string | US city |
| `state` | string | State abbreviation |
| `region` | string | `northeast` / `southeast` / `midwest` / `west` / `southwest` |
| `opened_date` | date | Store opening date |

### Weighted Distribution Logic

Following the aircraft script's pattern of using `random.choices` with explicit weight lists:

**Seasonal multipliers** (applied to daily transaction volume):
- Jan–Feb: 0.8 (post-holiday dip)
- Mar–Apr: 1.1 (spring buying)
- May–Jun: 1.2 (summer prep)
- Jul–Aug: 0.9 (summer lull)
- Sep–Oct: 1.3 (back-to-school, fall running season)
- Nov–Dec: 1.5 (holiday peak)

**Category purchase frequency** (weighted selection):
- Running Shoes: 30%
- Casual Shoes: 20%
- Apparel: 25%
- Accessories: 15%
- Equipment: 10%

**Customer segment behaviors:**

| Segment | Avg orders/year | Avg basket size | Discount sensitivity | Brand loyalty |
|---------|----------------|-----------------|---------------------|---------------|
| Loyal | 12 | 2.5 items | Low (0–10%) | High (repeats same brands) |
| Occasional | 4 | 1.5 items | Medium (5–15%) | Medium |
| New | 2 | 1.2 items | High (10–25%) | Low (explores) |
| Bargain Hunter | 8 | 3.0 items | Very high (15–30%) | Low (price-driven) |

**Time-of-day distribution** (purchase hour):
- 6am–9am: 10%
- 9am–12pm: 20%
- 12pm–2pm: 15% (lunch break spike)
- 2pm–5pm: 15%
- 5pm–9pm: 30% (evening peak)
- 9pm–6am: 10%

### Script Structure

```python
#!/usr/bin/env python3
"""
Generate large-scale retail transaction dataset (500,000 transactions)
Integrates with existing Neo4j product catalog from load_products.py
"""

import csv
import random
from datetime import datetime, timedelta

# Import product catalog for referential integrity
from load_products import PRODUCTS, CATEGORIES

def generate_customers(num_customers: int = 5000) -> list[dict]: ...
def generate_stores(num_stores: int = 20) -> list[dict]: ...
def generate_transactions(
    products: list[dict],
    customers: list[dict],
    stores: list[dict],
    num_transactions: int = 500_000,
    start_date: datetime = datetime(2023, 1, 1),
    end_date: datetime = datetime(2024, 12, 31),
) -> list[dict]: ...
def generate_reviews(transactions: list[dict], review_rate: float = 0.10) -> list[dict]: ...
def generate_inventory_snapshots(
    products: list[dict],
    transactions: list[dict],
    start_date: datetime = datetime(2023, 1, 1),
    end_date: datetime = datetime(2024, 12, 31),
) -> list[dict]: ...
def write_csv(records: list[dict], filename: str) -> None: ...
def main() -> None: ...
```

### Output

Running `python generate_transactions.py` produces:

```
data/
  transactions.csv        (~500,000 rows, ~80MB)
  customers.csv           (5,000 rows)
  reviews.csv             (50,000 rows)
  inventory_snapshots.csv (100,000+ rows)
  stores.csv              (20 rows)
```

## Expanding the Product Catalog in `load_products.py`

The current `load_products.py` creates 16 products. For the lakehouse integration to be meaningful, the catalog should grow to **500+ products** so that transaction analytics reveal interesting patterns across a realistic assortment. The expansion approach:

### Category Expansion

| Category | Current | Target | New Subcategories |
|----------|---------|--------|-------------------|
| Running Shoes | 5 | 60 | Trail, Road, Racing, Stability, Motion Control |
| Casual Shoes | 3 | 50 | Sneakers, Sandals, Boots, Slip-ons |
| Apparel | 3 | 120 | Tops, Bottoms, Jackets, Base Layers, Compression |
| Accessories | 3 | 80 | Watches, Socks, Hydration, Bags, Sunglasses, Headbands |
| Equipment | 2 | 60 | Recovery, Strength, Yoga, Cardio |
| **New: Nutrition** | 0 | 50 | Energy Gels, Protein, Electrolytes, Bars |
| **New: Outdoor** | 0 | 80 | Hiking Boots, Backpacks, Trekking Poles, Rain Gear |

### Brand Expansion

Current: 8 brands. Target: 40+ brands spanning athletic (Nike, Adidas, New Balance, ASICS, Brooks, Hoka, Saucony, On), lifestyle (Vans, Converse, Puma), outdoor (Salomon, Merrell, The North Face, Patagonia, Arc'teryx), tech (Garmin, Coros, Apple, Polar), nutrition (GU, Clif, Nuun, Tailwind), and equipment (TriggerPoint, Theraband, Hyperice, Manduka).

### Implementation

Rather than hardcoding 500 product dicts, `load_products.py` gains a `generate_expanded_catalog()` function that:

1. Defines category/subcategory/brand matrices with price ranges.
2. Generates product names programmatically (e.g., `"{brand} {model_word} {subcategory_suffix}"`).
3. Assigns realistic attributes per category (weight, cushion, material, etc.).
4. Creates product descriptions from templates.
5. Generates more BOUGHT_TOGETHER and SIMILAR_TO relationships based on category/brand overlap.
6. The original 16 products remain as-is for backward compatibility with existing tests.

## Databricks Lakehouse Setup

### Delta Lake Table Creation

Following the pattern from the aircraft workshop's `lakehouse_tables.py`, the retail tables are created in Unity Catalog:

```sql
-- Catalog: retail-assistant-workshop
-- Schema: retail-schema
-- Volume: retail-volume (holds the uploaded CSVs)

CREATE TABLE IF NOT EXISTS transactions
USING DELTA
AS SELECT
  transaction_id,
  order_id,
  customer_id,
  product_id,
  product_name,
  category,
  brand,
  CAST(quantity AS INT) AS quantity,
  CAST(unit_price AS DOUBLE) AS unit_price,
  CAST(discount_pct AS DOUBLE) AS discount_pct,
  CAST(total_price AS DOUBLE) AS total_price,
  CAST(purchase_date AS TIMESTAMP) AS purchase_date,
  CAST(purchase_hour AS INT) AS purchase_hour,
  day_of_week,
  channel,
  store_id,
  payment_method,
  CAST(returned AS BOOLEAN) AS returned,
  CAST(return_date AS TIMESTAMP) AS return_date,
  return_reason
FROM read_files('/Volumes/retail-assistant-workshop/retail-schema/retail-volume/transactions.csv',
  format => 'csv', header => true);

-- Partition by month for efficient time-range queries
-- (mirrors the aircraft sensor_readings partitioned by sensor_id)
```

### Column Comments for Genie

Following the aircraft workshop pattern where column comments help Genie understand the schema:

```sql
COMMENT ON TABLE transactions IS 'Retail purchase transactions over 2 years (2023-2024). Each row is a line item in an order. Use order_id to group line items into baskets.';
COMMENT ON COLUMN transactions.product_id IS 'Product identifier matching the Neo4j product catalog. Use for cross-referencing with graph-based recommendations.';
COMMENT ON COLUMN transactions.total_price IS 'Final price after discount: quantity * unit_price * (1 - discount_pct).';
COMMENT ON COLUMN transactions.channel IS 'Purchase channel: online, in_store, or mobile_app.';
```

## Agent Integration

### New Agent Tools for Lakehouse Queries

The agent gains new tools that query Databricks via the SQL connector or REST API:

| Tool | Input | Returns | Backend |
|------|-------|---------|---------|
| `get_sales_trends` | category, brand, time_period | Sales volume and revenue over time | Databricks SQL |
| `get_product_reviews` | product_id, min_rating | Review summary with average rating | Databricks SQL |
| `get_customer_insights` | customer_id | Purchase history, preferences, lifetime value | Databricks SQL |
| `get_trending_products` | category, time_window | Products ranked by recent sales velocity | Databricks SQL |
| `get_inventory_trends` | product_id, days | Stock level history and availability forecast | Databricks SQL |
| `get_basket_analysis` | product_id | Products frequently bought together (large-scale) | Databricks SQL |

These complement the existing Neo4j tools:

| Existing Neo4j Tool | How Lakehouse Enhances It |
|---------------------|--------------------------|
| `search_products` | Agent can combine graph search with "top rated" or "trending" from lakehouse |
| `get_recommendations` | Graph recommendations enriched with "customers also bought" from transaction data |
| `check_inventory` | Current stock from Neo4j, stock trend from lakehouse snapshots |
| `get_related_products` | Graph relationships + co-purchase patterns from transaction history |

### Multi-Agent Routing (Following the Aircraft Pattern)

The aircraft workshop uses a Databricks AgentBricks supervisor that routes to either a Genie Agent (lakehouse SQL) or Neo4j MCP Agent (graph Cypher). The retail assistant can adopt the same pattern:

```
User: "What running shoes are trending and have good reviews?"

LangGraph Router:
  1. get_trending_products(category="Running Shoes", time_window="30d")
     → Databricks SQL: SELECT product_id, COUNT(*) as sales
       FROM transactions WHERE category = 'Running Shoes'
       AND purchase_date > CURRENT_DATE - INTERVAL 30 DAYS
       GROUP BY product_id ORDER BY sales DESC LIMIT 10

  2. get_product_reviews(product_ids=[...], min_rating=4)
     → Databricks SQL: SELECT product_id, AVG(rating), COUNT(*)
       FROM reviews WHERE product_id IN (...) AND rating >= 4
       GROUP BY product_id

  3. search_products(query="trending running shoes")
     → Neo4j: Vector search + graph traversal for descriptions and relationships

  4. Agent synthesizes: trending sales data + review scores + product details + graph relationships
```

### Connection Configuration

Add to the existing `Settings` Pydantic model:

```python
class Settings(BaseSettings):
    # Existing
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    openai_api_key: str

    # New: Databricks
    databricks_host: str | None = None          # e.g., adb-1234567890.1.azuredatabricks.net
    databricks_http_path: str | None = None     # e.g., /sql/1.0/warehouses/abc123
    databricks_token: str | None = None         # Personal access token or service principal
    databricks_catalog: str = "retail_assistant"
    databricks_schema: str = "retail"
```

When Databricks settings are not configured, the lakehouse tools are simply not registered with the agent, and the system degrades gracefully to Neo4j-only mode (identical to the current behavior).

## Implementation Plan

### Phase L1: Data Generation

- Create `generate_transactions.py` following the `generate_removal_data.py` pattern.
- Read product IDs from `load_products.py` for referential integrity.
- Generate all 5 CSV files into a `data/` directory.
- Verify row counts, column types, and foreign key consistency.

### Phase L2: Product Catalog Expansion

- Add `generate_expanded_catalog()` to `load_products.py`.
- Expand from 16 to 500+ products across 7 categories and 40+ brands.
- Preserve original 16 products for backward compatibility.
- Regenerate transaction data against the expanded catalog.

### Phase L3: Databricks Table Setup

- Create a notebook or script that uploads CSVs to a Unity Catalog Volume.
- Create Delta Lake tables with proper types and partitioning.
- Add column comments for Genie compatibility.
- Verify tables are queryable from SQL Warehouse.

### Phase L4: Lakehouse Agent Tools

- Add `tools/lakehouse.py` with Databricks SQL tools using the `@tool` decorator and Pydantic input schemas.
- Add `databricks-sql-connector` to `pyproject.toml` as an optional dependency.
- Register lakehouse tools in `create_tools()` only when Databricks settings are configured.
- Each tool parameterizes all values (no string interpolation into SQL).

### Phase L5: Agent Integration

- Update the system prompt to mention the agent's ability to analyze sales trends, reviews, and purchase history.
- Test multi-source queries that combine Neo4j graph data with Databricks analytics.
- Extend `test_api.py` with lakehouse-specific tests.

### Phase L6: Workshop Lab Notebooks

- Create Databricks notebooks for workshop participants:
  - Lab: Upload CSVs and create Delta Lake tables.
  - Lab: Explore transaction data with SQL queries.
  - Lab: Connect the AI agent to both Neo4j and Databricks.
  - Lab: Ask multi-source questions and observe routing.

## Success Criteria

- `generate_transactions.py` produces 500,000+ transactions with valid product ID foreign keys matching the Neo4j catalog.
- All 5 CSV files load cleanly into Databricks Delta Lake tables.
- The AI agent answers time-series questions (trends, reviews, basket analysis) by querying Databricks.
- The AI agent answers graph questions (recommendations, related products, preferences) by querying Neo4j.
- When Databricks is not configured, the agent works identically to before (graceful degradation).
- Workshop participants can complete the lab in under 45 minutes.

## Stakeholders

- Workshop participants learning to build AI agents with dual-database backends.
- The Neo4j developer relations team maintaining the retail assistant example.
- The Databricks partnership team demonstrating joint Neo4j + Databricks value.
