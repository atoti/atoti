.PHONY: env check format test review restore

env:
	pip install --quiet --disable-pip-version-check uv
	uv sync
	uv run pre-commit install

check: env
	uv run ruff format --check .

format: env
	uv run ruff format .

test: check format
	uv run python tests/execute_notebooks.py

review:
	uv run jupyter-lab

restore:
	git restore --staged '**/content.mv.db'
	git restore '**/content.mv.db'