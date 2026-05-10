"""Compatibility entry point for knowledge checks."""

import sys

from retail_agent.demos.check_knowledge import *  # noqa: F401,F403
from retail_agent.demos.check_knowledge import check_knowledge


if __name__ == "__main__":
    sys.exit(check_knowledge())
