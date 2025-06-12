import argparse
from exclusion_utils import get_target_notebooks, get_excluded_notebook_groups
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


def map_target_args(target_args) -> list[str] | None:
    """
    Parse the --target argument and map user-friendly group names to exclusion group names.
    - Accepts comma-separated values, trims whitespace, and normalizes names.
    - If only 'ce' is present, return 'DEFAULT_ONLY' to indicate only default notebooks.
    - If only 'licensed' or 'long-running' is present, return only that group.
    - If 'ce' is present with other groups, include default notebooks plus the specified groups.
    """
    group_map = {
        "licensed": "Atoti Locked Notebooks",
        "unlocked": "Atoti Locked Notebooks",
        "long-running": "Long Running Notebooks",
    }
    # Normalize and flatten all arguments
    normalized = [
        part.strip().lower().replace(" ", "-")
        for arg in target_args
        for part in arg.split(",")
    ]
    if normalized == ["ce"]:
        return "DEFAULT_ONLY"
    if normalized == ["licensed"]:
        return [group_map["licensed"]]
    if normalized == ["long-running"]:
        return [group_map["long-running"]]
    # If 'ce' is present with other groups, include default notebooks plus the specified groups
    has_ce = "ce" in normalized
    filtered = [key for key in normalized if key != "ce"]
    groups = set()
    for key in filtered:
        groups.add(group_map.get(key, key))
    if has_ce:
        return ["DEFAULT_PLUS"] + list(groups)
    return list(groups)


def collect_notebooks(target_groups) -> list[str]:
    """
    Return the list of notebooks to test based on the target groups.
    - If target_groups is None, return all default notebooks (with all groups included).
    - If target_groups is 'DEFAULT_ONLY', return only default notebooks (with all groups excluded).
    - If only one group is present, return only that group's notebooks.
    - If 'DEFAULT_PLUS' is present, return default notebooks plus the specified groups.
    - Otherwise, return all default notebooks plus the specified groups.
    """
    if target_groups is None:
        return get_target_notebooks()
    if target_groups == "DEFAULT_ONLY":
        return get_target_notebooks(include=None)
    if (
        isinstance(target_groups, list)
        and target_groups
        and target_groups[0] == "DEFAULT_PLUS"
    ):
        # Default notebooks plus the specified groups
        groups = target_groups[1:]
        default = get_target_notebooks(include=None)
        group_notebooks = []
        exclusion_groups = get_excluded_notebook_groups()
        for group in groups:
            group_notebooks.extend(exclusion_groups.get(group, []))
        # Remove duplicates while preserving order
        all_notebooks = default + [nb for nb in group_notebooks if nb not in default]
        return all_notebooks
    if len(target_groups) == 1:
        group = target_groups[0]
        exclusion_groups = get_excluded_notebook_groups()
        return exclusion_groups.get(group, [])
    return get_target_notebooks(include=target_groups)


def main():
    parser = argparse.ArgumentParser(
        description="Run notebook tests with optional group inclusions."
    )
    parser.add_argument(
        "--target",
        nargs="*",
        required=True,
        help="Comma-separated list of group names to target (e.g. --target=ce,licensed,long-running)",
    )
    args = parser.parse_args()

    target_groups = map_target_args(args.target)

    # Set environment variables if 'Atoti Locked Notebooks' (licensed) is targeted
    if target_groups and any(g == "Atoti Locked Notebooks" for g in target_groups):
        os.environ.setdefault("GOOGLE_CLIENT_ID", "dummy-google-client-id")
        os.environ.setdefault("GOOGLE_CLIENT_SECRET", "dummy-google-client-secret")
        os.environ.setdefault("AUTH0_CLIENT_ID", "dummy-auth0-client-id")
        os.environ.setdefault("AUTH0_CLIENT_SECRET", "dummy-auth0-client-secret")
        os.environ.setdefault("AUTH0_DOMAIN", "dummy-auth0-domain")

    notebooks = collect_notebooks(target_groups)
    for nb in notebooks:
        print(nb)

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

    sys.exit(pytest.main(pytest_args))


if __name__ == "__main__":
    main()
