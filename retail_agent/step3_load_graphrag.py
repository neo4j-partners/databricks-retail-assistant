"""Compatibility entry point for loading GraphRAG data."""

import asyncio
import sys

from retail_agent.deployment.load_graphrag import *  # noqa: F401,F403
from retail_agent.deployment.load_graphrag import load_graphrag


if __name__ == "__main__":
    sys.exit(asyncio.run(load_graphrag()))
