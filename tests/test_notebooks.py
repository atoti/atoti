import argparse
import os
import platform as pf
import sys
import pytest
from exclusion_utils import resolve_target_notebooks, add_and_validate_target_args


def set_licensed_env_vars():
    """
    Ensure required environment variables for licensed notebooks are set in the OS environment.
    Raise an error if any are missing.
    """
    required_vars = [
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "AUTH0_CLIENT_ID",
        "AUTH0_CLIENT_SECRET",
        "AUTH0_DOMAIN",
    ]
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables for licensed notebooks: {', '.join(missing)}"
        )


def get_num_workers() -> int | str:
    """
    Determine the number of parallel workers for pytest-xdist.
    On macOS 13 GitHub runners, reduce workers to avoid CPU overload.
    """
    is_mac_github_runner = pf.system() == "Darwin" and pf.release() == "22.6.0"
    cpu_count = os.cpu_count()
    if is_mac_github_runner and cpu_count and cpu_count > 2:
        return cpu_count - 2
    return "auto"


def main():
    # Parse and validate CLI arguments
    parser = argparse.ArgumentParser(
        description="Test target notebooks with Pytest and Nbmake."
    )
    args = add_and_validate_target_args(parser)

    # Normalize all target group names for consistent logic
    normalized_targets = []
    for arg in args.target:
        split_targets = arg.split(",")
        for part in split_targets:
            normalized = part.strip().lower().replace(" ", "-")
            if normalized:
                normalized_targets.append(normalized)

    # Check if the user requested the 'licensed' group and set env vars if needed
    licensed_requested = "licensed" in normalized_targets
    if licensed_requested:
        set_licensed_env_vars()

    # Resolve the list of notebooks to test
    notebooks = resolve_target_notebooks(args.target)
    for nb in notebooks:
        print(nb)

    # Prepare pytest arguments for notebook testing
    html_report = f"reports/report-{pf.system()}-{pf.release()}.html"
    junit_report = f"reports/junit-{pf.system()}-{pf.release()}.xml"
    pytest_args = [
        "--nbmake",
        "--nbmake-timeout=7200",
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
