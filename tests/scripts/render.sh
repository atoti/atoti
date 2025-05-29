#!/bin/bash
set -euo pipefail

wait_for_jupyter() {
  local host="${1:-127.0.0.1}"
  local port="${2:-8888}"
  local timeout="${3:-30}"
  local url="http://${host}:${port}"
  local start_time=$(date +%s)
  while true; do
    if curl -s --max-time 1 "$url" > /dev/null; then
      return 0
    fi
    sleep 0.5
    local now=$(date +%s)
    if (( now - start_time > timeout )); then
      echo "Timed out waiting for JupyterLab on $host:$port" >&2
      return 1
    fi
  done
}

echo "Starting Jupyter Lab..."
trap 'pkill -f jupyter-lab' INT TERM EXIT
nohup uv run jupyter-lab \
  --allow-root --no-browser --ip=0.0.0.0 --port=8888 \
  --NotebookApp.token='' --NotebookApp.password='' \
  > /dev/null 2>&1 &
wait_for_jupyter 127.0.0.1 8888 5
echo "JupyterLab is running"

uv run python tests/render_notebooks.py