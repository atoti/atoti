from exclusion_utils import get_included_notebooks
import pytest
import platform as pf
import os
import sys

platform = pf.system()
release = pf.release()

# Reduce number of workers on macos-13 GitHub Action runner to avoid CPU overload
if platform == "Darwin" and release == "22.6.0":
    num_workers = os.cpu_count() - 2
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
        f"--html=reports/report-{platform}-{release}.html",
        "--self-contained-html",
        f"--junitxml=reports/junit-{platform}-{release}.xml",
    ] + notebooks
    sys.exit(pytest.main(pytest_args))
