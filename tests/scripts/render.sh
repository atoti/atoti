#!/bin/bash
set -euo pipefail

trap 'pkill -f jupyter-lab' INT TERM EXIT

uv run playwright install
uv run playwright install-deps

nohup uv run jupyter-lab \
  --allow-root --no-browser --ip=0.0.0.0 --port=8888 \
  --NotebookApp.token='' --NotebookApp.password='' \
  > jupyter.log 2>&1 &

uv run python tests/render_notebooks.py