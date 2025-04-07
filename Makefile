.PHONY: test lint build review restore-content-db

build:
	uv sync

lint: build
	uv run ruff format .

test: lint
	uv pip install pytest-xdist pytest-html nbmake 
	uv run python execute_notebooks.py

review:
	uv pip install nbdime 
	uv run jupyter-lab

restore-content-db:
	git restore '**/content.mv.db'