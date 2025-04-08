.PHONY: test lint build review restore-content-db

build:
	uv sync

lint: build
	uv run ruff format .

test: lint
	uv run python tests/execute_notebooks.py

review:
	uv run jupyter-lab

restore-content-db:
	git restore '**/content.mv.db'