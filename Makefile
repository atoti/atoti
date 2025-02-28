.PHONY: test lint build review

build:
	uv sync

lint: build
	uv run ruff format --check .

test: lint
	uv run python tests/execute_notebooks.py

review:
	uv pip install nbdime
	uv run jupyter-lab