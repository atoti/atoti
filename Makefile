SHELL := /bin/bash

.PHONY: env check format test test-licensed test-long test-all render render-licensed render-long review restore upgrade

# Set up the Python environment and install pre-commit hooks
env:
	pip install --quiet --disable-pip-version-check uv
	uv sync
	uv run pre-commit install

# Check code formatting using ruff
check:
	uv run ruff format --check .

# Format code using ruff
format:
	uv run ruff format .

# Run default notebook tests
test: check format
	uv run python tests/test_notebooks.py --target=default

# Run tests for licensed notebooks
test-licensed: check format
	./tests/scripts/install_dq.sh
	uv run python tests/test_notebooks.py --target=licensed

# Run tests for long-running notebooks
test-long: check format
	uv run python tests/test_notebooks.py --target=long-running

# Run all notebook tests
test-all: check format
	./tests/scripts/install_dq.sh
	uv run python tests/test_notebooks.py --target=default,licensed,long-running

# Render default notebooks in JupyterLab using Playwright
render: check format
	uv run playwright install
	uv run playwright install-deps
	./tests/scripts/render.sh default

# Render licensed notebooks in JupyterLab using Playwright
render-licensed: check format
	./tests/scripts/install_dq.sh
	uv run playwright install
	uv run playwright install-deps
	./tests/scripts/render.sh licensed

# Render long-running notebooks in JupyterLab using Playwright
render-long: check format
	uv run playwright install
	uv run playwright install-deps
	./tests/scripts/render.sh long-running

# Render all notebooks in JupyterLab using Playwright
render-all: check format
	./tests/scripts/install_dq.sh
	uv run playwright install
	uv run playwright install-deps
	./tests/scripts/render.sh default licensed long-running

# Launch JupyterLab for review
review:
	uv run jupyter-lab --port=8888

# Restore Atoti database files to their original state
restore:
	git restore --staged '**/content.mv.db'
	git restore '**/content.mv.db'

# Run all tests and render notebooks
upgrade:
	make test-all && make render-all