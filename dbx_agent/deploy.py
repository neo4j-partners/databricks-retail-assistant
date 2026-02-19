"""Deploy prototype agent to Databricks using agents.deploy().

Ported from aircraft_analyst/src/graph_agent/deploy.py. Four-step
pipeline: log model -> register to UC -> deploy -> wait for ready.

Usage:
    # Deploy:
    uv run python -m dbx_agent.deploy

    # Delete:
    RETAIL_AGENT_RUN_MODE=delete uv run python -m dbx_agent.deploy

Prerequisites:
    1. Databricks CLI configured (databricks auth login)
    2. Unity Catalog: retail_assistant.retail must exist
    3. For Step 3 (not Step 2): Databricks secrets for Neo4j
"""

import os
import sys
import time
from pathlib import Path

from dbx_agent.config import CONFIG, DeployConfig, RunMode


def _get_package_dir() -> Path:
    """Resolve the dbx_agent/ directory.

    Uses __file__ when available (local CLI). On Databricks, Python
    files run through IPython where __file__ is not defined, so we
    fall back to inspecting the config module's file location (which
    *is* set because it was imported normally, not executed directly).
    """
    # Try __file__ first (works when running as `python -m dbx_agent.deploy`)
    this_file = globals().get("__file__")
    if this_file:
        return Path(this_file).parent

    # Databricks Workspace: the directly-executed file has no __file__,
    # but imported modules do. config.py is a sibling, so use its path.
    import dbx_agent.config as _cfg

    cfg_file = getattr(_cfg, "__file__", None)
    if cfg_file:
        return Path(cfg_file).parent

    raise RuntimeError(
        "Cannot determine package directory: neither __file__ nor "
        "dbx_agent.config.__file__ is available."
    )


def get_current_user() -> str:
    """Get the current Databricks user email."""
    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        return w.current_user.me().user_name
    except Exception:
        return os.environ.get("DATABRICKS_USER", "default")


# =============================================================================
# STEP 1: LOG MODEL TO MLFLOW
# =============================================================================


def log_model_to_mlflow(config: DeployConfig) -> tuple:
    """Log the agent model to MLflow using Models from Code."""
    import mlflow

    print("=" * 60)
    print("STEP 1: Log Model to MLflow")
    print("=" * 60)

    mlflow.set_registry_uri("databricks-uc")

    current_user = get_current_user()
    experiment_name = config.get_experiment_name(current_user)
    mlflow.set_experiment(experiment_name)
    print(f"Experiment: {experiment_name}")

    # The serving.py file — MLflow loads this via Models from Code
    model_file = _get_package_dir() / "serving.py"
    if not model_file.exists():
        raise FileNotFoundError(f"Model file not found: {model_file}")
    print(f"Model file: {model_file}")

    # Code files imported by serving.py at runtime (via code_paths on sys.path)
    pkg_dir = _get_package_dir()
    code_files = [
        str(pkg_dir / "agent.py"),
        str(pkg_dir / "context.py"),
        str(pkg_dir / "diagnostics_tool.py"),
        str(pkg_dir / "memory_tool.py"),
        str(pkg_dir / "product_search.py"),
    ]

    # neo4j-agent-memory wheel
    wheel_name = "neo4j_agent_memory-0.0.1-py3-none-any.whl"
    wheel_path = None

    # Check env var override first
    env_wheel = os.environ.get("RETAIL_AGENT_WHEEL_PATH")
    if env_wheel:
        candidate = Path(env_wheel)
        if candidate.is_dir():
            candidate = candidate / wheel_name
        if candidate.exists():
            wheel_path = candidate

    # Fallback: Databricks Volumes
    if not wheel_path:
        volumes_candidate = Path(f"/Volumes/{config.catalog}/{config.schema}/retail_volume/libs/{wheel_name}")
        if volumes_candidate.exists():
            wheel_path = volumes_candidate

    # Fallback: local relative paths (sibling repo)
    if not wheel_path:
        project_root = _get_package_dir().parent.parent
        for candidate in [
            project_root / ".." / "agent-memory" / "dist" / wheel_name,
            project_root / ".." / ".." / "neo4j-labs" / "agent-memory" / "dist" / wheel_name,
        ]:
            candidate = candidate.resolve()
            if candidate.exists():
                wheel_path = candidate
                break

    if wheel_path:
        code_files.append(str(wheel_path))
        print(f"Including wheel: {wheel_path}")
    else:
        print(f"WARNING: Wheel '{wheel_name}' not found. Searched:")
        print(f"  - RETAIL_AGENT_WHEEL_PATH env var")
        print(f"  - /Volumes/{config.catalog}/{config.schema}/retail_volume/libs/")
        print(f"  - ../agent-memory/dist/ (local)")
        print(f"  - ../../neo4j-labs/agent-memory/dist/ (local)")

    print(f"Including code files: {[Path(f).name for f in code_files]}")

    pip_requirements = [
        "mlflow>=3.1",
        "databricks-agents>=0.15.0",
        "langgraph>=1.0.8",
        "langchain-core>=0.3.0",
        "databricks-langchain>=0.15.0",
        "neo4j>=5.20.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "openai>=1.0.0",
        "nest-asyncio>=1.5.0",
    ]

    # Include the bundled wheel in pip_requirements so it installs at serving time
    if wheel_path:
        pip_requirements.append(f"code/{wheel_name}")

    with mlflow.start_run(run_name=config.run_name):
        log_kwargs = {
            "artifact_path": config.artifact_path,
            "python_model": str(model_file),
            "pip_requirements": pip_requirements,
            "code_paths": code_files,
        }

        model_info = mlflow.pyfunc.log_model(**log_kwargs)
        print(f"Model logged: {model_info.model_uri}")
        return model_info, model_info.model_uri


# =============================================================================
# STEP 2: REGISTER TO UNITY CATALOG
# =============================================================================


def register_model_to_uc(model_uri: str, config: DeployConfig):
    """Register the model to Unity Catalog."""
    import mlflow

    print()
    print("=" * 60)
    print("STEP 2: Register to Unity Catalog")
    print("=" * 60)

    registered_model = mlflow.register_model(
        model_uri=model_uri,
        name=config.uc_model_name,
    )
    print(f"Registered: {registered_model.name}")
    print(f"Version: {registered_model.version}")
    return registered_model


# =============================================================================
# STEP 3: DEPLOY USING agents.deploy()
# =============================================================================


def deploy_agent(config: DeployConfig, model_version: int):
    """Deploy the agent using Databricks Agent Framework."""
    from databricks import agents

    print()
    print("=" * 60)
    print("STEP 3: Deploy with agents.deploy()")
    print("=" * 60)

    print(f"Model: {config.uc_model_name}")
    print(f"Version: {model_version}")
    print(f"Scale to zero: {config.scale_to_zero}")

    env_vars = config.get_environment_vars()
    if env_vars:
        print("\nEnvironment variables:")
        for key, value in env_vars.items():
            display_value = "{{secrets/...}}" if "secrets/" in value else value
            print(f"  {key}: {display_value}")
    else:
        print("\nNo environment variables (Step 2 — no secrets needed)")

    deploy_kwargs = {
        "scale_to_zero_enabled": config.scale_to_zero,
    }
    if env_vars:
        deploy_kwargs["environment_vars"] = env_vars

    deployment = agents.deploy(
        config.uc_model_name,
        model_version,
        **deploy_kwargs,
    )

    print()
    print("Deployment initiated!")
    print(f"Query endpoint: {deployment.query_endpoint}")
    return deployment


# =============================================================================
# STEP 4: WAIT FOR ENDPOINT TO BE READY
# =============================================================================


def wait_for_endpoint(config: DeployConfig, endpoint_name: str) -> bool:
    """Wait for the endpoint to be ready."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import EndpointStateReady

    print()
    print("=" * 60)
    print("STEP 4: Wait for Endpoint Ready")
    print("=" * 60)

    print(f"Endpoint: {endpoint_name}")
    print(f"Max wait: {config.max_wait_seconds} seconds")
    print()

    w = WorkspaceClient()
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > config.max_wait_seconds:
            print(f"\nTimeout after {elapsed:.0f} seconds")
            return False

        try:
            endpoint = w.serving_endpoints.get(endpoint_name)
            state = endpoint.state.ready if endpoint.state else None

            if state == EndpointStateReady.READY:
                print(f"\nEndpoint is READY after {elapsed:.0f} seconds")
                return True

            print(f"  [{elapsed:>5.0f}s] State: {state}")
            time.sleep(10)

        except Exception as e:
            print(f"  [{elapsed:>5.0f}s] Checking... ({e})")
            time.sleep(10)


# =============================================================================
# DELETE ENDPOINT
# =============================================================================


def delete_endpoint(config: DeployConfig) -> bool:
    """Delete the serving endpoint."""
    from databricks.sdk import WorkspaceClient

    print()
    print("=" * 60)
    print("DELETE ENDPOINT")
    print("=" * 60)

    endpoint_name = config.resolved_endpoint_name
    print(f"Endpoint to delete: {endpoint_name}")

    w = WorkspaceClient()
    try:
        try:
            endpoint = w.serving_endpoints.get(endpoint_name)
            print(f"Found endpoint: {endpoint.name}")
        except Exception:
            print(f"Endpoint '{endpoint_name}' does not exist")
            return True

        print("Deleting endpoint...")
        w.serving_endpoints.delete(endpoint_name)
        print("Endpoint deleted successfully")
        return True
    except Exception as e:
        print(f"Error deleting endpoint: {e}")
        return False


# =============================================================================
# MAIN
# =============================================================================


def print_config(config: DeployConfig) -> None:
    """Print the current configuration."""
    print("=" * 60)
    print("CONFIGURATION")
    print("=" * 60)
    print(f"Run Mode:            {config.run_mode.value}")
    print(f"Unity Catalog Model: {config.uc_model_name}")
    print(f"Endpoint Name:       {config.resolved_endpoint_name}")
    print(f"LLM Endpoint:        {config.llm_endpoint}")
    print(f"Scale to Zero:       {config.scale_to_zero}")
    if config.run_mode == RunMode.DEPLOY:
        print(f"Experiment Pattern:  {config.experiment_name_pattern}")
        print(f"Wait for Ready:      {config.wait_for_ready}")
    print()
    print("Override with env vars: RETAIL_AGENT_CATALOG, RETAIL_AGENT_SCHEMA, etc.")
    print()


def run_deploy(config: DeployConfig) -> int:
    """Run the deployment workflow."""
    try:
        model_info, model_uri = log_model_to_mlflow(config)
        registered_model = register_model_to_uc(model_uri, config)
        deployment = deploy_agent(config, registered_model.version)

        if config.wait_for_ready:
            endpoint_name = (
                deployment.endpoint_name
                if hasattr(deployment, "endpoint_name")
                else config.resolved_endpoint_name
            )
            if not wait_for_endpoint(config, endpoint_name):
                print("\nWarning: Endpoint not ready within timeout")
                print("Check the Databricks UI for status")

        print()
        print("=" * 60)
        print("DEPLOYMENT COMPLETE!")
        print("=" * 60)
        print()
        print(f"Query endpoint: {deployment.query_endpoint}")
        print()
        print("To test:")
        print("  uv run python -m dbx_agent.check_endpoint")
        print()
        return 0

    except Exception as e:
        print()
        print("=" * 60)
        print(f"DEPLOYMENT FAILED: {e}")
        print("=" * 60)
        import traceback

        traceback.print_exc()
        return 1


def run_delete(config: DeployConfig) -> int:
    """Run the delete workflow."""
    if delete_endpoint(config):
        print()
        print("=" * 60)
        print("DELETE COMPLETE!")
        print("=" * 60)
        return 0
    else:
        print()
        print("=" * 60)
        print("DELETE FAILED!")
        print("=" * 60)
        return 1


def main() -> int:
    """Main entry point."""
    print()
    print("=" * 60)
    print("RETAIL AGENT PROTOTYPE DEPLOYMENT")
    print("=" * 60)
    print()

    config = CONFIG
    print_config(config)

    if config.run_mode == RunMode.DELETE:
        return run_delete(config)
    else:
        return run_deploy(config)


if __name__ == "__main__":
    sys.exit(main())
