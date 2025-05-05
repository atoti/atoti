.PHONY: check build lint test review restore-content-db

build:
	uv sync
	uv pip install pre-commit
	uv run pre-commit install

check: build
	uv run ruff format --check .

lint: build
	uv run ruff format .

test: lint
	uv run python tests/execute_notebooks.py

review:
	uv run jupyter-lab

restore-content-db:
	git restore '**/content.mv.db'