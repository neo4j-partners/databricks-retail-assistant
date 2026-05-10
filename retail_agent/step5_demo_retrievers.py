"""Compatibility entry point for retriever demos."""

import sys

from retail_agent.demos.demo_retrievers import *  # noqa: F401,F403
from retail_agent.demos.demo_retrievers import demo_retrievers


if __name__ == "__main__":
    sys.exit(demo_retrievers())
