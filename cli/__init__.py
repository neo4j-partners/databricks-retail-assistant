"""Retail assistant CLI wired to databricks-job-runner."""

from pathlib import Path

from databricks_job_runner import Runner
from databricks_job_runner.submit import submit_job


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
        params = self._job_params()
        run_name = f"{self.run_name_prefix}: {script}"

        if params:
            print(f"  Params:   {len(params)} env values from .env")

        wheel_path: str | None = None
        if self.wheel_package and script.startswith(f"run_{self.wheel_package}"):
            wheel_name = self.find_wheel()
            if wheel_name:
                wheel_path = f"{self.wheel_volume_dir}/{wheel_name}"
                print(f"  Wheel:    {wheel_path}")

        run_id = submit_job(
            self.ws,
            compute=self._compute(compute_mode),
            workspace_dir=self.config.databricks_workspace_dir,
            script_name=script,
            run_name=run_name,
            params=params,
            wheel_path=wheel_path,
            no_wait=no_wait,
            scripts_dir=self.scripts_dir,
        )

        print()
        print("Next steps:")
        print(f"  View logs:          {self.cli_command} logs {run_id}")
        if self.config.databricks_volume_path:
            print(f"  List results:       {self.cli_command} download --list results")
            print(f"  Download results:   {self.cli_command} download results/<filename>")


runner = RetailAgentRunner(
    run_name_prefix="retail_agent",
    project_dir=Path(__file__).resolve().parent.parent,
    wheel_package="retail_agent",
    scripts_dir="jobs",
)
