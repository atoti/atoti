from exclusion_utils import get_included_notebooks
import pytest
import sys
import platform
import os

# Reduce number of workers on macos-13 GitHub Action runner to avoid CPU overload
if platform.system() == "Darwin" and platform.release() == "22.6.0":
    num_workers = os.cpu_count() - 1
else:
    num_workers = "auto"

notebooks = get_included_notebooks()
for notebook in notebooks:
    print(notebook)

if __name__ == "__main__":
    pytest_args = [
        "--nbmake",
        "--nbmake-timeout=600",
        "-n",
        f"{num_workers}",
        "--dist",
        "worksteal",
        "-v",
        f"--html=reports/report-{sys.platform}.html",
        "--self-contained-html",
        f"--junitxml=reports/junit-{sys.platform}.xml",
    ] + notebooks
    sys.exit(pytest.main(pytest_args))
