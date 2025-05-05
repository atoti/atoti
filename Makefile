.PHONY: check setup lint test review restore-content-db

setup:
	uv sync
	uv pip install pre-commit
	uv run pre-commit install

check: setup
	uv run ruff format --check .

lint: setup
	uv run ruff format .

test: lint
	uv run python tests/execute_notebooks.py

review:
	uv run jupyter-lab

restore-content-db:
	git restore '**/content.mv.db'