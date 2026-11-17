#!/usr/bin/env bash
# Scheduled update for Linux/macOS (e.g. cron: 0 3 1 * * /path/to/repo/scripts/run_update.sh)
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON=python3
PYTHONPATH=src exec "$PYTHON" -m gaia_pipeline run --all --incremental
