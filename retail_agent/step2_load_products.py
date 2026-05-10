"""Compatibility entry point for loading product data."""

import sys

from retail_agent.deployment.load_products import *  # noqa: F401,F403
from retail_agent.deployment.load_products import load_sample_data


if __name__ == "__main__":
    sys.exit(load_sample_data())
