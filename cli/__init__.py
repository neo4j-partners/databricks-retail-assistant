"""Retail assistant CLI wired to databricks-job-runner."""

from pathlib import Path

from databricks.sdk.service.jobs import PythonWheelTask, RunResultState, SubmitTask
from databricks_job_runner import Runner
from databricks_job_runner.errors import RunnerError


ENTRY_POINTS = {
    "retail-graph-concierge-deploy": "retail_graph_concierge_deploy",
    "retail-graph-concierge-load-products": "retail_graph_concierge_load_products",
    "retail-graph-concierge-load-graphrag": "retail_graph_concierge_load_graphrag",
    "retail-graph-concierge-demo": "retail_graph_concierge_demo",
    "retail-graph-concierge-demo-retrievers": "retail_graph_concierge_demo_retrievers",
    "retail-graph-concierge-check-knowledge": "retail_graph_concierge_check_knowledge",
    "retail-graph-concierge-deploy-supervisor": "retail_graph_concierge_deploy_supervisor",
}


class RetailAgentRunner(Runner):
    """Runner that keeps local Neo4j setup secrets out of job parameters."""

    _LOCAL_ONLY_ENV_KEYS = frozenset({
        "DATABRICKS_CONFIG_PROFILE",
        "NEO4J_URI",
        "NEO4J_PASSWORD",
    })

    def _job_params(self) -> list[str]:
        params = self.config.env_params(secret_keys=self.secret_keys)
        return [
            param
            for param in params
            if param.partition("=")[0] not in self._LOCAL_ONLY_ENV_KEYS
        ]

    def submit(
        self,
        script: str,
        *,
        no_wait: bool = False,
        compute_mode: str | None = None,
    ) -> None:
        if script not in ENTRY_POINTS:
            available = "\n  ".join(sorted(ENTRY_POINTS))
            raise RunnerError(
                f"Unknown Retail Graph Concierge entry point: {script}\n"
                f"Available entry points:\n  {available}"
            )

        params = self._job_params()
        run_name = f"{self.run_name_prefix}: {script}"

        if params:
            print(f"  Params:   {len(params)} env values from .env")

        wheel_name = self.find_wheel()
        if not wheel_name:
            raise RunnerError(
                "No retail_agent wheel found in dist/. "
                "Run: uv run python -m cli upload --wheel"
            )
        wheel_path = f"{self.wheel_volume_dir}/{wheel_name}"
        print(f"  Wheel:    {wheel_path}")

        compute = self._compute(compute_mode)
        compute.validate(self.ws)

        print("Submitting wheel entry point")
        print(f"  Entry:    {script}")
        print(f"  Run name: {run_name}")
        print("---")

        entry_point = ENTRY_POINTS[script]
        task = SubmitTask(
            task_key="run_entry_point",
            python_wheel_task=PythonWheelTask(
                package_name=self.wheel_package or "retail_agent",
                entry_point=entry_point,
                parameters=params if params else None,
            ),
        )
        task = compute.decorate_task(task, wheel_path)

        waiter = self.ws.jobs.submit(
            run_name=run_name,
            tasks=[task],
            environments=compute.environments(wheel_path),
        )

        run_id: int | None = waiter.run_id
        if run_id is None:
            raise RunnerError("Databricks did not return a run_id.")
        print(f"  Run ID:   {run_id}")

        if no_wait:
            print("\nJob submitted (--no-wait). Check status in the Databricks UI.")
        else:
            print("  Waiting for completion...")
            run = waiter.result()
            result_state = run.state.result_state if run.state else None
            state_name = result_state.value if result_state else "UNKNOWN"
            page_url = run.run_page_url or ""

            print(f"\n  Result:   {state_name}")
            if page_url:
                print(f"  URL:      {page_url}")
            if result_state != RunResultState.SUCCESS:
                raise RunnerError(f"Job finished with non-success state: {state_name}")
            print("\nJob complete.")

        print()
        print("Next steps:")
        print(f"  View logs:          {self.cli_command} logs {run_id}")
        if self.config.databricks_volume_path:
            print(f"  List results:       {self.cli_command} download --list results")
            print(f"  Download results:   {self.cli_command} download results/<filename>")

    def upload_all(self) -> None:
        """No-op because jobs run Python wheel entry points directly."""
        print("No job scripts to upload.")
        print("Retail Graph Concierge jobs run from the uploaded wheel entry points.")
        print("Run: uv run python -m cli upload --wheel")

    def validate(self, file: str | None = None) -> None:
        """Validate compute and wheel-entry-point configuration."""
        self._compute().validate(self.ws)
        if file and file not in ENTRY_POINTS:
            available = "\n  ".join(sorted(ENTRY_POINTS))
            raise RunnerError(
                f"Unknown Retail Graph Concierge entry point: {file}\n"
                f"Available entry points:\n  {available}"
            )
        print()
        print("Available wheel entry points:")
        for entry_point in sorted(ENTRY_POINTS):
            print(f"  {entry_point}")
        print()
        print("Validation complete.")


runner = RetailAgentRunner(
    run_name_prefix="retail_agent",
    project_dir=Path(__file__).resolve().parent.parent,
    wheel_package="retail_agent",
)
