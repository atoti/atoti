SHELL := /bin/bash

.PHONY: env check format test review restore upgrade

env:
	pip install --quiet --disable-pip-version-check uv
	uv sync
	uv run pre-commit install

check: env
	uv run ruff format --check .

format: env
	uv run ruff format .

test: check format
	uv run python tests/test_notebooks.py --target=ce

test-licensed: check format
	uv run python tests/test_notebooks.py --target=licensed

test-long: check format
	uv run python tests/test_notebooks.py --target=long-running

test-all: check format
	uv run python tests/test_notebooks.py --target=ce,licensed,long-running

render: check format
	uv run playwright install
	uv run playwright install-deps
	./tests/scripts/render.sh

review:
	uv run jupyter-lab --port=8888

restore:
	git restore --staged '**/content.mv.db'
	git restore '**/content.mv.db'

upgrade:
	make test && make render