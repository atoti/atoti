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

web-render: check format
	nohup uv run jupyter-lab --no-browser --port=8888 --NotebookApp.token='' --NotebookApp.password='' > jupyter.log 2>&1 &
	uv run python tests/execute_notebooks.py

review:
	uv run jupyter-lab --port=8888

restore:
	git restore --staged '**/content.mv.db'
	git restore '**/content.mv.db'