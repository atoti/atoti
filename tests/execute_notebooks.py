import glob
from pathlib import Path
import pytest
import sys
import pandas as pd

nest_asyncio.apply()  # Apply the patch to allow nested event loops
_MAIN = "main.ipynb"

# Maintain exclusion list only for academy and tech tutorials
# Add to exclude use cases which are upgraded to latest but cannot be tested
NOTEBOOKS_DIRECTORY = Path("notebooks")
DATA_PREPROCESSING_NOTEBOOKS = [
    "var-benchmark/data_generator.ipynb",  # Timeout
]

NOTEBOOKS_WTIH_ALT_CONNECTORS = [
    f"auto-cube/{_MAIN}",  # requires user csv input
    f"auto-cube/main-advanced.ipynb",  # requires user csv input
    f"var-benchmark/{_MAIN}",  # requires data generation (large data volume)
    f"directquery-vector/{_MAIN}",  # Direct Query notebook
    f"directquery-intro/{_MAIN}",  # Direct Query notebook
    f"virtual-hierarchies/{_MAIN}",  # Direct Query notebook
]

ATOTI_UNLOCKED_NOTEBOOKS = [
    "security-implementation/01-Basic-authentication.ipynb",
    "security-implementation/02-OIDC-Auth0.ipynb",
    "security-implementation/03-OIDC-Google.ipynb",
    "security-implementation/04-LDAP.ipynb",
    f"security-implementation/{_MAIN}",
    f"internationalization/{_MAIN}",
]

# some notebooks may have dependencies conflict with the latest Atoti version
# to be listed here if it cannot be tested but is still upgraded
NOTEBOOKS_WITH_ERRORS = []

NOTEBOOKS_ACADEMY = ["introduction-to-atoti/main.ipynb"]  # error on purpose

INVALID_NAMED_NOTEBOOKS = ["Untitled"]

NOTEBOOKS_TO_SKIP = sorted(
    DATA_PREPROCESSING_NOTEBOOKS
    + NOTEBOOKS_WITH_ERRORS
    + NOTEBOOKS_WTIH_ALT_CONNECTORS
    + ATOTI_UNLOCKED_NOTEBOOKS
    + NOTEBOOKS_ACADEMY
    + INVALID_NAMED_NOTEBOOKS
)

# Gather the list of notebooks under the project directory
nb_list = [
    nb_path.replace("\\", "/")
    for nb_path in glob.glob(f"./*/**/*.ipynb", recursive=True)
    if not "ipynb_checkpoints" in nb_path
]

# 1. Exclude the list of notebooks added in this script
# 2. Exclude the list of non-maintained notebooks generated from the README program
#    https://github.com/activeviam/bd-atoti-gallery/tree/main/readme-generator
exclusion_list = pd.read_csv("./tests/test_exclusion.txt", header=None)[0].to_list()
notebooks = [
    nb_path
    for nb_path in nb_list
    if not any(exclude_nb in str(nb_path) for exclude_nb in NOTEBOOKS_TO_SKIP)
    and not any(exclude_nb in str(nb_path) for exclude_nb in exclusion_list)
]

for notebook in notebooks:
    print(notebook)

if __name__ == "__main__":
    pytest_args = [
        "--nbmake",
        "--nbmake-timeout=600",
        "-n",
        "auto",
        "-v",
        f"--html=reports/report-{sys.platform}.html",
        "--self-contained-html",
        f"--junitxml=reports/junit-{sys.platform}.xml",
    ] + notebooks
    sys.exit(pytest.main(pytest_args))
