#!/usr/bin/env bash
# Run fixit_sandbox tests using the project's uv-managed venv.
set -euo pipefail

cd "$(dirname "$0")/.."
uv run python -m pytest fixit_sandbox/ -v "$@"
