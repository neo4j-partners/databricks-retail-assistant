"""Compatibility entry point for the deployed agent demo."""

import sys

from retail_agent.demos.demo_agent import *  # noqa: F401,F403
from retail_agent.demos.demo_agent import check_endpoint


if __name__ == "__main__":
    sys.exit(check_endpoint())
