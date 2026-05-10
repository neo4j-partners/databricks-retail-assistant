"""Compatibility entry point for deploying Retail Graph Concierge."""

import sys

from retail_agent.deployment.deploy_agent import *  # noqa: F401,F403
from retail_agent.deployment.deploy_agent import main


if __name__ == "__main__":
    sys.exit(main())
