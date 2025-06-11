from exclusion_utils import get_included_notebooks
import pytest
import platform as pf
import os
import sys


def get_num_workers() -> int | str:
    """
    Determine the number of parallel workers for pytest-xdist.
    On macOS 13 GitHub runners, reduce workers to avoid CPU overload.
    """
    if pf.system() == "Darwin" and pf.release() == "22.6.0":
        return os.cpu_count() - 2
    return "auto"


def get_groups_to_include(args) -> list[str]:
    """
    Map command-line arguments to exclusion group names to include in tests.
    Supported args: 'licensed', 'long-running'.
    """
    arg_map = {
        "licensed": "Atoti Unlocked Notebooks",
        "long-running": "Long Running Notebooks",
    }
    return [arg_map[arg] for arg in args if arg in arg_map]


def collect_notebooks(groups_to_include: list[str]) -> list[str]:
    """
    Get the list of notebooks to test, including any specified exclusion groups.
    """
    if not groups_to_include:
        return get_included_notebooks()
    if len(groups_to_include) == 1:
        return get_included_notebooks(keep=groups_to_include[0])
    return get_included_notebooks(keep=groups_to_include)


def main():
    # Parse command-line arguments for special groups
    groups_to_include = get_groups_to_include(sys.argv[1:])
    notebooks = collect_notebooks(groups_to_include)

    # Print the list of notebooks to be tested
    print("Notebooks to be tested:")
    for notebook in notebooks:
        print(f"  - {notebook}")

    # Prepare pytest arguments
    num_workers = get_num_workers()
    platform_name = pf.system()
    release = pf.release()
    pytest_args = [
        "--nbmake",
        "--nbmake-timeout=600",
        "-n",
        f"{num_workers}",
        "--dist",
        "worksteal",
        "-v",
        f"--html=reports/report-{platform_name}-{release}.html",
        "--self-contained-html",
        f"--junitxml=reports/junit-{platform_name}-{release}.xml",
    ] + notebooks

    # Run pytest with the constructed arguments
    sys.exit(pytest.main(pytest_args))


if __name__ == "__main__":
    main()
