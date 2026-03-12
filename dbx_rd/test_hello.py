"""Minimal test script to verify remote execution on Databricks.

Prints environment info so we can confirm:
1. The script actually ran on the cluster
2. Python and Spark are available
3. We can see the output in the job run
"""

import sys
import os

print("=" * 60)
print("dbx_rd: Remote execution test")
print("=" * 60)
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")
print(f"Working directory: {os.getcwd()}")
print(f"DATABRICKS_RUNTIME_VERSION: {os.environ.get('DATABRICKS_RUNTIME_VERSION', 'not set')}")

# Verify Spark is available
try:
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    print(f"Spark version: {spark.version}")
    print(f"Spark app name: {spark.sparkContext.appName}")
except Exception as e:
    print(f"Spark not available: {e}")

# Verify mlflow is available (needed for Phase 2 adapters)
try:
    import mlflow
    print(f"mlflow version: {mlflow.__version__}")
except ImportError:
    print("mlflow: not installed")

# Verify neo4j driver is available
try:
    import neo4j
    print(f"neo4j driver version: {neo4j.__version__}")
except ImportError:
    print("neo4j: not installed")

print("=" * 60)
print("SUCCESS: Remote execution verified")
print("=" * 60)
