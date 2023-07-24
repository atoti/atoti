import os
import nbformat
import logging

from nbconvert.preprocessors import ExecutePreprocessor
from pathlib import Path

_MAIN = "main.ipynb"

NOTEBOOKS_DIRECTORY = Path("./..")
DATA_PREPROCESSING_NOTEBOOKS = [
    # tech tutorials
    "var-benchmark/data_generator.ipynb",  # Timeout
]
NOTEBOOKS_WTIH_ALT_CONNECTORS = [
    f"auto-cube/{_MAIN}",    
    f"var-benchmark/{_MAIN}",  # data generation timeout TO FIX
]
UNLOCK_NOTEBOOKS = [
    "security-implementation/01-Basic-authentication.ipynb",
    "security-implementation/02-OIDC-Auth0.ipynb",
    "security-implementation/03-OIDC-Google.ipynb",
    "security-implementation/04-LDAP.ipynb",
    f"security-implementation/{_MAIN}",
    f"internationalization/{_MAIN}",
]

NOTEBOOKS_TO_SKIP = sorted(
    DATA_PREPROCESSING_NOTEBOOKS
    + NOTEBOOKS_WTIH_ALT_CONNECTORS
    + UNLOCK_NOTEBOOKS
)


def execute_notebooks():
    notebooks_path = sorted(
        [
            notebook_path
            for notebook_path in NOTEBOOKS_DIRECTORY.glob("02-technical-tutorials/**/*.ipynb")
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
