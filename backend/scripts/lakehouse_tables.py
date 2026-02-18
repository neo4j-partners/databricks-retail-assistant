#!/usr/bin/env python3
"""Create Delta Lake tables in Databricks Unity Catalog from generated CSVs.

This script:
1. Uploads CSV files from data/lakehouse/ to a Unity Catalog Volume.
2. Creates Delta Lake tables with proper types and partitioning.
3. Adds column comments for Genie compatibility.

Prerequisites:
- Databricks workspace with Unity Catalog enabled
- A SQL Warehouse running
- Environment variables: DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN
- Optional: DATABRICKS_CATALOG (default: retail_assistant),
            DATABRICKS_SCHEMA (default: retail)
"""

import argparse
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "lakehouse"


class DatabricksSettings(BaseSettings):
    """Databricks connection and Unity Catalog settings."""

    host: str = Field(alias="DATABRICKS_HOST")
    http_path: str = Field(alias="DATABRICKS_HTTP_PATH")
    token: SecretStr = Field(alias="DATABRICKS_TOKEN")
    catalog: str = Field(default="retail_assistant", alias="DATABRICKS_CATALOG")
    schema_name: str = Field(default="retail", alias="DATABRICKS_SCHEMA")
    volume: str = Field(default="retail_volume", alias="DATABRICKS_VOLUME")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def volume_path(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema_name}/{self.volume}"

    @property
    def fqn(self) -> str:
        """Fully-qualified ``catalog.schema`` prefix for SQL statements."""
        return f"{self.catalog}.{self.schema_name}"


CSV_FILES = [
    "transactions.csv",
    "customers.csv",
    "reviews.csv",
    "inventory_snapshots.csv",
    "stores.csv",
]


# ---------------------------------------------------------------------------
# Structured table definitions
# ---------------------------------------------------------------------------


class TableDef(BaseModel):
    """A Delta Lake table definition with its CREATE SQL and column comments."""

    name: str
    select_sql: str
    table_comment: str = ""
    comments: dict[str, str] = Field(default_factory=dict)


def _build_table_defs(settings: DatabricksSettings) -> list[TableDef]:
    """Build table definitions using runtime settings."""
    fqn = settings.fqn
    vol = settings.volume_path

    return [
        TableDef(
            name=f"{fqn}.transactions",
            select_sql=f"""
                SELECT
                    transaction_id, order_id, customer_id, product_id, product_name,
                    category, brand,
                    CAST(quantity AS INT) AS quantity,
                    CAST(unit_price AS DOUBLE) AS unit_price,
                    CAST(discount_pct AS DOUBLE) AS discount_pct,
                    CAST(total_price AS DOUBLE) AS total_price,
                    CAST(purchase_date AS TIMESTAMP) AS purchase_date,
                    CAST(purchase_hour AS INT) AS purchase_hour,
                    day_of_week, channel, store_id, payment_method,
                    CAST(returned AS BOOLEAN) AS returned,
                    CASE WHEN return_date = '' THEN NULL ELSE CAST(return_date AS TIMESTAMP) END AS return_date,
                    CASE WHEN return_reason = '' THEN NULL ELSE return_reason END AS return_reason
                FROM read_files('{vol}/transactions.csv', format => 'csv', header => true)
            """,
            table_comment="Retail purchase transactions over 2 years (2023-2024). Each row is a line item in an order. Use order_id to group line items into baskets.",
            comments={
                "transaction_id": "Unique line item identifier (TXN prefix + date + sequence).",
                "order_id": "Order identifier grouping line items into a single basket/purchase. Multiple rows can share the same order_id.",
                "customer_id": "Customer identifier (CUST prefix). Links to customers table.",
                "product_id": "Product identifier matching the Neo4j product catalog. Use for cross-referencing with graph-based recommendations.",
                "total_price": "Final price after discount: quantity * unit_price * (1 - discount_pct).",
                "channel": "Purchase channel: online, in_store, or mobile_app.",
                "store_id": "Store identifier for in_store purchases. Empty string for online/mobile_app. Links to stores table.",
                "returned": "Whether the item was returned (true/false).",
                "return_reason": "Reason for return: wrong_size, defective, changed_mind, or not_as_described. NULL if not returned.",
            },
        ),
        TableDef(
            name=f"{fqn}.customers",
            select_sql=f"""
                SELECT
                    customer_id, segment,
                    CAST(signup_date AS DATE) AS signup_date,
                    preferred_channel, city, state, age_group
                FROM read_files('{vol}/customers.csv', format => 'csv', header => true)
            """,
            table_comment="Customer dimension table with 5,000 customers across 4 segments: loyal, occasional, new, bargain_hunter.",
            comments={
                "segment": "Customer segment: loyal (high frequency, low discount), occasional (medium), new (low frequency, high discount), bargain_hunter (high frequency, high discount).",
                "preferred_channel": "Customer preferred purchase channel: online, in_store, or mobile_app.",
            },
        ),
        TableDef(
            name=f"{fqn}.reviews",
            select_sql=f"""
                SELECT
                    review_id, transaction_id, customer_id, product_id,
                    CAST(rating AS INT) AS rating,
                    CAST(review_date AS TIMESTAMP) AS review_date,
                    CAST(verified_purchase AS BOOLEAN) AS verified_purchase
                FROM read_files('{vol}/reviews.csv', format => 'csv', header => true)
            """,
            table_comment="Product reviews linked to transactions. Ratings 1-5, weighted toward positive (mean ~4.0). All reviews are verified purchases.",
            comments={
                "rating": "Product rating from 1 (worst) to 5 (best). Distribution weighted toward positive (mean ~4.0).",
                "verified_purchase": "Always true — all reviews are linked to actual transactions.",
            },
        ),
        TableDef(
            name=f"{fqn}.inventory_snapshots",
            select_sql=f"""
                SELECT
                    CAST(snapshot_date AS DATE) AS snapshot_date,
                    product_id,
                    CAST(stock_level AS INT) AS stock_level,
                    CAST(units_sold AS INT) AS units_sold,
                    CAST(units_received AS INT) AS units_received,
                    stock_status
                FROM read_files('{vol}/inventory_snapshots.csv', format => 'csv', header => true)
            """,
            table_comment="Daily inventory levels per product over 2 years. Tracks stock level, units sold, units received, and stock status.",
            comments={
                "stock_status": "Stock status: in_stock, low_stock, or out_of_stock based on current level vs reorder point.",
                "units_received": "Units received from replenishment. Non-zero when stock dipped below reorder point.",
            },
        ),
        TableDef(
            name=f"{fqn}.stores",
            select_sql=f"""
                SELECT
                    store_id, store_name, city, state, region,
                    CAST(opened_date AS DATE) AS opened_date
                FROM read_files('{vol}/stores.csv', format => 'csv', header => true)
            """,
            table_comment="Store dimension table with 20 physical retail locations across US regions.",
        ),
    ]


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def get_connection(settings: DatabricksSettings):
    """Create a Databricks SQL connection."""
    from databricks import sql as databricks_sql

    return databricks_sql.connect(
        server_hostname=settings.host,
        http_path=settings.http_path,
        access_token=settings.token.get_secret_value(),
    )


def upload_csvs_via_files_api(settings: DatabricksSettings) -> None:
    """Upload CSV files using the Databricks REST Files API.

    Streams file content rather than loading entirely into memory.
    """
    import requests

    host = settings.host.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.token.get_secret_value()}"}
    base_url = f"https://{host}/api/2.0/fs/files"

    print(f"\nUploading CSVs to {settings.volume_path}/ via Files API...")

    for csv_file in CSV_FILES:
        filepath = DATA_DIR / csv_file
        if not filepath.exists():
            print(f"  SKIP {csv_file} (not found)")
            continue

        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"  Uploading {csv_file} ({size_mb:.1f} MB)...", end=" ", flush=True)

        url = f"{base_url}{settings.volume_path}/{csv_file}"
        with open(filepath, "rb") as f:
            resp = requests.put(
                url,
                headers={**headers, "Content-Type": "application/octet-stream"},
                data=f,  # streams the file
            )

        if resp.status_code in (200, 201, 204):
            print("OK")
        else:
            print(f"FAILED ({resp.status_code}: {resp.text[:200]})")

    print("  Upload complete.")


def upload_csvs_via_sql(settings: DatabricksSettings, connection) -> None:
    """Upload CSV files via SQL PUT commands."""
    print(f"\nUploading CSVs to {settings.volume_path}/ via SQL...")

    with connection.cursor() as cursor:
        cursor.execute(f"CREATE CATALOG IF NOT EXISTS {settings.catalog}")
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {settings.fqn}")
        cursor.execute(f"CREATE VOLUME IF NOT EXISTS {settings.fqn}.{settings.volume}")

    for csv_file in CSV_FILES:
        filepath = DATA_DIR / csv_file
        if not filepath.exists():
            print(f"  SKIP {csv_file} (not found)")
            continue

        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"  Uploading {csv_file} ({size_mb:.1f} MB)...", end=" ", flush=True)

        dest = f"{settings.volume_path}/{csv_file}"
        with connection.cursor() as cursor:
            cursor.execute(f"PUT '{dest}' OVERWRITE")
        print("OK")

    print("  Upload complete.")


def create_tables(connection, table_defs: list[TableDef]) -> None:
    """Create Delta Lake tables from the uploaded CSVs."""
    print("\nCreating Delta Lake tables...")

    with connection.cursor() as cursor:
        for table_def in table_defs:
            print(f"  Creating {table_def.name}...", end=" ", flush=True)
            cursor.execute(
                f"CREATE OR REPLACE TABLE {table_def.name} USING DELTA AS {table_def.select_sql}"
            )
            print("OK")

    print("  All tables created.")


def _escape_sql_string(value: str) -> str:
    """Escape single quotes for SQL string literals."""
    return value.replace("'", "''")


def add_comments(connection, table_defs: list[TableDef]) -> None:
    """Add table and column comments for Genie compatibility."""
    print("\nAdding comments...")
    count = 0

    with connection.cursor() as cursor:
        for table_def in table_defs:
            if table_def.table_comment:
                escaped = _escape_sql_string(table_def.table_comment)
                cursor.execute(
                    f"COMMENT ON TABLE {table_def.name} IS '{escaped}'"
                )
                count += 1

            for col_name, col_comment in table_def.comments.items():
                escaped = _escape_sql_string(col_comment)
                cursor.execute(
                    f"COMMENT ON COLUMN {table_def.name}.{col_name} IS '{escaped}'"
                )
                count += 1

    print(f"  Added {count} comments.")


def verify_tables(connection, table_defs: list[TableDef]) -> None:
    """Verify tables are queryable and show row counts."""
    print("\nVerifying tables...")

    with connection.cursor() as cursor:
        for table_def in table_defs:
            cursor.execute(f"SELECT COUNT(*) FROM {table_def.name}")
            row = cursor.fetchone()
            count = row[0] if row else "?"
            print(f"  {table_def.name}: {count:,} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up Databricks lakehouse tables")
    parser.add_argument(
        "--upload-method", choices=["sql", "api"], default="api",
        help="Upload method: 'api' (REST Files API, default) or 'sql' (SQL PUT)",
    )
    parser.add_argument("--skip-upload", action="store_true", help="Skip CSV upload")
    parser.add_argument("--skip-tables", action="store_true", help="Skip table creation")
    args = parser.parse_args()

    # Verify CSVs exist
    missing = [f for f in CSV_FILES if not (DATA_DIR / f).exists()]
    if missing and not args.skip_upload:
        print(f"ERROR: Missing CSV files in {DATA_DIR}: {missing}")
        print("Run: python -m backend.scripts.generate_transactions --expanded")
        return

    settings = DatabricksSettings()  # type: ignore[call-arg]
    table_defs = _build_table_defs(settings)
    connection = get_connection(settings)

    try:
        if not args.skip_upload:
            if args.upload_method == "api":
                upload_csvs_via_files_api(settings)
            else:
                upload_csvs_via_sql(settings, connection)

        if not args.skip_tables:
            create_tables(connection, table_defs)
            add_comments(connection, table_defs)
            verify_tables(connection, table_defs)
    finally:
        connection.close()

    print("\nDone!")


if __name__ == "__main__":
    main()
