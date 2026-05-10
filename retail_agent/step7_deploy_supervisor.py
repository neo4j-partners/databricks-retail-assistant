"""Compatibility entry point for the supervisor deployment stub."""

import sys

from retail_agent.deployment.deploy_supervisor import *  # noqa: F401,F403
from retail_agent.deployment.deploy_supervisor import main


if __name__ == "__main__":
    sys.exit(main())
