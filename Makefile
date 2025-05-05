.PHONY: check build lint test review restore-content-db

check:
	uv run ruff format --check .

build:
	uv sync
	uv pip install pre-commit
	uv run pre-commit install

lint: build
	uv run ruff format .

test: lint
	uv run python tests/execute_notebooks.py

review:
	uv run jupyter-lab

restore-content-db:
	git restore '**/content.mv.db'