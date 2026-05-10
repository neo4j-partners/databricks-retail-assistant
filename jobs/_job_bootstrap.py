"""Helpers for Databricks job scripts submitted by databricks_job_runner."""

from __future__ import annotations

import os
import runpy
import sys


def inject_params() -> None:
    """Load KEY=VALUE job parameters into os.environ."""
    remaining: list[str] = []
    for arg in sys.argv[1:]:
        if "=" in arg and not arg.startswith("-"):
            key, _, value = arg.partition("=")
            os.environ.setdefault(key, value)
        else:
            remaining.append(arg)
    sys.argv[1:] = remaining


def run_module(module_name: str) -> None:
    """Run a packaged retail_agent module as if it were executed directly."""
    inject_params()
    try:
        runpy.run_module(module_name, run_name="__main__")
    except SystemExit as exc:
        if exc.code in (0, None):
            return
        raise
