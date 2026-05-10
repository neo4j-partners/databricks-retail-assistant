"""Deploy the multi-agent supervisor (STUB).

Placeholder entry point matching the step1..step6 pattern. The Mosaic AI
multi-agent supervisor + Genie wiring is not yet implemented. See
retail_agent.agent.supervisor for the skeleton and the README
"Supervisor (stub)" section for the full TODO list.
"""

import sys

from retail_agent.deployment.runtime import inject_env_params


def main() -> int:
    inject_env_params()

    print("=" * 72)
    print("STUB: step7_deploy_supervisor.py is a placeholder.")
    print("The multi-agent supervisor + Genie wiring is not yet implemented.")
    print("See retail_agent.agent.supervisor for the skeleton and TODOs.")
    print("=" * 72)
    return 1


if __name__ == "__main__":
    sys.exit(main())
