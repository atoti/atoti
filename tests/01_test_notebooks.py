import argparse
import os
import platform as pf
import sys
import pytest
from utils.exclusion_logic import resolve_target_notebooks, add_and_validate_target_args


def get_num_workers() -> int | str:
    """
    Determine the number of parallel workers for pytest-xdist.
    On GitHub runner, reduce workers to 2.
    Otherwise on local machine, set workers to 'auto'.
    """
    is_github_runner = os.environ.get("GITHUB_ACTIONS") == "true"
    if is_github_runner:
        return 2
    else:
        return "auto"


def main():
    # Parse and validate CLI arguments
    parser = argparse.ArgumentParser(
        description="Test target notebooks with Pytest and Nbmake."
    )
    args = add_and_validate_target_args(parser)
    notebooks = resolve_target_notebooks(args.target)
    for nb in notebooks:
        print(nb)

    # Determine timeout based on whether 'long-running' is in the targets
    normalized_targets = []
    for arg in args.target:
        for part in arg.split(","):
            normalized = part.strip().lower().replace(" ", "-")
            if normalized:
                normalized_targets.append(normalized)
    if "long-running" in normalized_targets:
        nbmake_timeout = 7200
    else:
        nbmake_timeout = 600

    # Prepare pytest arguments for notebook testing
    html_report = f"reports/report-{pf.system()}-{pf.release()}.html"
    junit_report = f"reports/junit-{pf.system()}-{pf.release()}.xml"
    pytest_args = [
        "--nbmake",
        f"--nbmake-timeout={nbmake_timeout}",
        "-n",
        f"{get_num_workers()}",
        "--dist",
        "worksteal",
        "-v",
        f"--html={html_report}",
        "--self-contained-html",
        f"--junitxml={junit_report}",
    ] + notebooks

    # Run pytest with the constructed arguments
    sys.exit(pytest.main(pytest_args))


if __name__ == "__main__":
    main()
