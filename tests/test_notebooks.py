from exclusion_utils import get_included_notebooks
import pytest
import sys

notebooks = get_included_notebooks()

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
