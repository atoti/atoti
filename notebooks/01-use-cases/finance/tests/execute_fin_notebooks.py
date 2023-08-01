import os
import nbformat
import logging

from nbconvert.preprocessors import ExecutePreprocessor
from pathlib import Path

_MAIN = "main.ipynb"

NOTEBOOKS_DIRECTORY = Path("./..")
DATA_PREPROCESSING_NOTEBOOKS = [
    # Financial notebooks
    # credit-risk
    "ifrs9/data-generation.ipynb",
    # operation risk notebooks
    "credit-card-fraud-detection/01-Synthetic-data-generation.ipynb",
    "credit-card-fraud-detection/02-AutoML-PyCaret-anomaly.ipynb",
    "credit-card-fraud-detection/03-AutoML-PyCaret-classification.ipynb",
    # Portfolio management
    "cvar-optimizer/01_data_generation.ipynb",
    # insurance notebooks
    "customer360/01-Dataupload-to-Vertica.ipynb",
]
NOTEBOOKS_WTIH_ALT_CONNECTORS = [
    "customer360/02-main-vertica-db.ipynb",
    f"real-time-risk/{_MAIN}",
    f"auto-cube/{_MAIN}",
]
NON_ATOTI_NOTEBOOKS = [
    # financial - treasury
    "collateral-shortfall-forecast/notebooks/0-download-stock-prices-data.ipynb",
    "collateral-shortfall-forecast/notebooks/1-data-preparation.ipynb",
    "collateral-shortfall-forecast/notebooks/2-data-exploration-decompose-time-series.ipynb",
    "collateral-shortfall-forecast/notebooks/3-data-exploration-partial-autocorrelations.ipynb",
    "collateral-shortfall-forecast/notebooks/4-create-machine-learning-pipeline.ipynb",
]
NOTEBOOKS_WITH_ERRORS = [
    "credit-card-fraud-detection/main.ipynb",  # pycaret dependency conflict with atoti 0.6.5 (numpy)
    "sbm/main.ipynb",  # broken in 0.6.3 https://github.com/atoti/atoti/issues/413
]
NOTEBOOKS_TO_SKIP = sorted(
    DATA_PREPROCESSING_NOTEBOOKS
    + NOTEBOOKS_WITH_ERRORS
    + NOTEBOOKS_WTIH_ALT_CONNECTORS
    + NON_ATOTI_NOTEBOOKS
)


def execute_notebooks():
    logging.basicConfig(format="%(asctime)s %(message)s", level=logging.INFO)

    notebooks_path = sorted(
        [
            notebook_path
            for notebook_path in NOTEBOOKS_DIRECTORY.glob("finance/**/*.ipynb")
            if "ipynb_checkpoints" not in str(notebook_path)
            and not any(
                str(notebook_path).endswith(os.path.normpath(exclude_nb))
                for exclude_nb in NOTEBOOKS_TO_SKIP
            )
        ]
    )

    for notebook_path in notebooks_path:
        logging.info(f"Starting execution of {notebook_path}")
        notebook = nbformat.read(notebook_path, as_version=4)
        ep = ExecutePreprocessor(timeout=300, kernel_name="python3")
        ep.preprocess(notebook, {"metadata": {"path": notebook_path.parent}})
        logging.info(f"Execution of {notebook_path} succeed")


if __name__ == "__main__":
    execute_notebooks()
