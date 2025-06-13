import argparse
import os
import platform as pf
import sys
import pytest
from exclusion_utils import get_target_notebooks, get_excluded_notebook_groups


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
    if pf.system() == "Darwin" and pf.release() == "22.6.0":
        return os.cpu_count() - 2
    return "auto"


def map_target_args(target_args):
    """
    Map user-friendly --target args to group names. Handles 'ce', 'licensed', 'long-running'.
    If 'ce' is present with other groups, combine default notebooks with those groups.
    If only 'ce' is present, return None to indicate the default set (all notebooks minus excluded groups).
    """
    group_map = {
        "licensed": "Atoti Locked Notebooks",
        "long-running": "Long Running Notebooks",
    }
    normalized = [
        part.strip().lower().replace(" ", "-")
        for arg in target_args
        for part in arg.split(",")
    ]
    if normalized == ["ce"]:
        return None  # Default set: all notebooks minus excluded groups
    if normalized == ["licensed"]:
        return [group_map["licensed"]]
    if normalized == ["long-running"]:
        return [group_map["long-running"]]
    has_ce = "ce" in normalized
    filtered = [key for key in normalized if key != "ce"]
    groups = set(group_map.get(key, key) for key in filtered)
    if has_ce and groups:
        return {"combine_default_with": list(groups)}
    return list(groups)


def collect_notebooks(target_groups) -> list[str]:
    """
    Return the list of notebooks to test based on the target groups.
    - If target_groups is None, return all notebooks minus any group exclusions.
    - If only one group is present, return only that group's notebooks.
    - If multiple groups are present, return only the notebooks from the specified groups.
    - Otherwise, if target_groups is a dict with 'combine_default_with', combine all notebooks minus group exclusions with those groups.
    """
    if target_groups is None:
        return get_target_notebooks(include_only=None)
    if isinstance(target_groups, list):
        if len(target_groups) == 1:
            group = target_groups[0]
            exclusion_groups = get_excluded_notebook_groups()
            return exclusion_groups.get(group, [])
        else:
            return get_target_notebooks(include_only=target_groups)
    if isinstance(target_groups, dict) and "combine_default_with" in target_groups:
        groups = target_groups["combine_default_with"]
        default = get_target_notebooks(include_only=None)
        group_notebooks = get_target_notebooks(include_only=groups)
        # Combine and deduplicate
        return sorted(set(default + group_notebooks))
    raise ValueError(f"Unexpected target_groups value: {target_groups!r}")


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
    if not args.target or all(not t.strip() for t in args.target):
        print(
            "Error: You must provide at least one group name to --target.",
            file=sys.stderr,
        )
        sys.exit(2)
    target_groups = map_target_args(args.target)
    if target_groups and any(
        g == "Atoti Locked Notebooks"
        for g in (target_groups if isinstance(target_groups, list) else [])
    ):
        set_licensed_env_vars()
    notebooks = collect_notebooks(target_groups)
    for nb in notebooks:
        print(nb)
    pytest_args = [
        "--nbmake",
        "--nbmake-timeout=600",
        "-n",
        f"{get_num_workers()}",
        "--dist",
        "worksteal",
        "-v",
        f"--html=reports/report-{pf.system()}-{pf.release()}.html",
        "--self-contained-html",
        f"--junitxml=reports/junit-{pf.system()}-{pf.release()}.xml",
    ] + notebooks
    sys.exit(pytest.main(pytest_args))


if __name__ == "__main__":
    main()
