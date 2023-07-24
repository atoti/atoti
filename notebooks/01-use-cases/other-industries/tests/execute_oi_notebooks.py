import os
import nbformat
import logging

from nbconvert.preprocessors import ExecutePreprocessor
from pathlib import Path

_MAIN = "main.ipynb"

NOTEBOOKS_DIRECTORY = Path("./..")
DATA_PREPROCESSING_NOTEBOOKS = [
    # other industries
    "ca-solar/01-nrel-data-sourcing.ipynb",
    "ca-solar/02-fire-data-sourcing.ipynb",
    "customer-churn/0_prepare_data.ipynb",
    "customer-churn/1_create_models.ipynb",
    "twitter/01_tweets_mining.ipynb",
    "twitter/02_sentiment.ipynb",
    "twitter/03_cryptocurrency_mining.ipynb",
    "influencers-analysis/notebooks/0_prepare_data.ipynb",
    "object-detection/main.ipynb",
    "object-detection/main_demo.ipynb",
    "object-detection/main_generate_csv.ipynb",
    "influencers-analysis/notebooks/1_create_topics.ipynb",
    "influencers-analysis/notebooks/2_analyze_topics.ipynb",
]
NOTEBOOKS_WTIH_ALT_CONNECTORS = [
    f"auto-cube/{_MAIN}",
    f"reddit/{_MAIN}",  # http 401 error TO FIX
    f"var-benchmark/{_MAIN}",  # data generation timeout TO FIX
]
NON_ATOTI_NOTEBOOKS = [
    # other industries
    "wildfire-prediction/notebooks/0-prepare-the-datasets.ipynb",
    "wildfire-prediction/notebooks/1-roll-the-datasets.ipynb",
    "wildfire-prediction/notebooks/2-extract-the-features-test.ipynb",
    "wildfire-prediction/notebooks/2-extract-the-features-train.ipynb",
    "wildfire-prediction/notebooks/2-extract-the-features-val.ipynb",
    "wildfire-prediction/notebooks/3-classification-with-OPLS.ipynb",
]
NOTEBOOKS_WITH_ERRORS = [
    f"geopricing/{_MAIN}",  # https://github.com/atoti/notebooks/runs/2829010222 TO FIX,
    # f"collateral-shortfall-forecast/notebooks/{_MAIN}",  # removed tsfresh due to conflict with protobuf
    "food-processing/main.ipynb",  # Validation of the RECORD file of mxnet-1.7.0.post1-py2.py3-none-win_amd64.whl failed
]
NOTEBOOKS_TO_SKIP = sorted(
    DATA_PREPROCESSING_NOTEBOOKS
    + NOTEBOOKS_WITH_ERRORS
    + NOTEBOOKS_WTIH_ALT_CONNECTORS
    + NON_ATOTI_NOTEBOOKS
)


def execute_notebooks():
    notebooks_path = sorted(
        [
            notebook_path
            for notebook_path in NOTEBOOKS_DIRECTORY.glob("other-industries/**/*.ipynb")
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
    logging.basicConfig(format="%(asctime)s %(message)s", level=logging.INFO)
    execute_notebooks()
