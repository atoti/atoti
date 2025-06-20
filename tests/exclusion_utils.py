from pathlib import Path
import glob
import os
from typing import List, Optional, Union
import sys


def get_excluded_notebook_groups(
    exclusion_file: str = "tests/test_exclusion.txt",
) -> dict:
    """
    Parse the exclusion file and return a dictionary mapping group names to lists of excluded notebook paths.
    Each group is defined by a header line (e.g., # --- GroupName ---), followed by notebook paths.
    """
    exclusion_path = Path(exclusion_file)
    groups = {}
    current_group = None
    if exclusion_path.exists():
        with exclusion_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue  # Skip empty lines
                if line.startswith("# ---") and line.endswith("---"):
                    # Start of a new group
                    current_group = line.strip("# -").strip()
                    groups[current_group] = []
                elif line.startswith("#"):
                    continue  # Skip comment lines
                else:
                    # Add notebook path to the current group
                    if current_group is None:
                        current_group = "Ungrouped"
                        groups.setdefault(current_group, [])
                    groups[current_group].append(line.replace("\\", "/"))
    return groups


def get_all_notebook_paths() -> List[str]:
    """
    Return all notebook paths in the project as relative paths with forward slashes.
    Ignores checkpoint files.
    """
    return [
        os.path.relpath(nb_path, ".").replace("\\", "/")
        for nb_path in glob.glob("./*/**/*.ipynb", recursive=True)
        if "ipynb_checkpoints" not in nb_path
    ]


def get_target_notebook_paths(
    include_only: Optional[Union[str, List[str]]] = None,
) -> List[str]:
    """
    Return a sorted list of notebook paths to include for testing.

    Args:
        include_only: Group name or list of group names to include. If None, returns all notebooks minus any group exclusions (as defined in the exclusion file).

    Returns:
        Sorted list of notebook paths to include.
    """
    notebook_paths = get_all_notebook_paths()
    exclusion_groups = get_excluded_notebook_groups()

    if include_only is None:
        # Gather all exclusions from all groups
        all_exclusions = set(nb for group in exclusion_groups.values() for nb in group)

        # Separate exclusions into files and directories
        excluded_files = {p for p in all_exclusions if p.endswith(".ipynb")}
        excluded_dirs = {
            p.rstrip("/") for p in all_exclusions if not p.endswith(".ipynb")
        }

        # Exclude if the path matches a file or is inside an excluded directory
        def is_excluded(notebook_path: str) -> bool:
            in_excluded_file = notebook_path in excluded_files
            in_excluded_dir = any(
                notebook_path.startswith(d + "/") for d in excluded_dirs
            )
            return in_excluded_file or in_excluded_dir

        included_notebooks = [nb for nb in notebook_paths if not is_excluded(nb)]
        return sorted(included_notebooks)

    # Ensure include_groups is always a set
    if isinstance(include_only, (list, tuple, set)):
        include_groups = set(include_only)
    else:
        include_groups = {include_only}

    # Gather all notebooks from the specified groups that exist in notebook_paths
    group_notebooks = set()
    for group in include_groups:
        notebooks_in_group = exclusion_groups.get(group, [])
        for nb in notebooks_in_group:
            if nb in notebook_paths:
                group_notebooks.add(nb)

    return sorted(group_notebooks)


def resolve_target_notebooks(target_args: list[str]) -> list[str]:
    """
    Return the list of notebooks to test based on the target groups.
    - If target_args is ['default'] or None, return all notebooks minus any group exclusions.
    - If only one group is present, return only that group's notebooks.
    - If multiple groups are present, return only the notebooks from the specified groups.
    - If 'default' is present with other groups, combine the set of all notebooks minus group exclusions, with those groups.
    """
    target_to_exclusion_group_map = {
        "licensed": "Atoti Locked Notebooks",
        "long-running": "Long Running Notebooks",
    }
    # Normalize all target arguments into a flat list of group keys
    normalized_targets = []
    for arg in target_args:
        split_targets = arg.split(",")
        for part in split_targets:
            normalized = part.strip().lower().replace(" ", "-")
            if normalized:
                normalized_targets.append(normalized)

    # Handle special cases for group selection
    only_default = normalized_targets == ["default"]
    only_licensed = normalized_targets == ["licensed"]
    only_long_running = normalized_targets == ["long-running"]
    has_default = "default" in normalized_targets
    filtered_targets = [key for key in normalized_targets if key != "default"]
    resolved_groups = set(
        target_to_exclusion_group_map.get(key, key) for key in filtered_targets
    )

    if only_default:
        return get_target_notebook_paths(include_only=None)
    if only_licensed:
        return get_target_notebook_paths(
            include_only=target_to_exclusion_group_map["licensed"]
        )
    if only_long_running:
        return get_target_notebook_paths(
            include_only=target_to_exclusion_group_map["long-running"]
        )
    if has_default and resolved_groups:
        default_notebooks = get_target_notebook_paths(include_only=None)
        group_notebooks = get_target_notebook_paths(include_only=resolved_groups)
        return sorted(set(default_notebooks + group_notebooks))
    if resolved_groups:
        return get_target_notebook_paths(include_only=resolved_groups)
    raise ValueError("No valid target groups specified.")


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
        "SNOWFLAKE_ACCOUNT_IDENTIFIER",
        "SNOWFLAKE_USERNAME",
        "SNOWFLAKE_PASSWORD",
        "SNOWFLAKE_ROLE",
        "SNOWFLAKE_WAREHOUSE",
        "SNOWFLAKE_DATABASE",
        "SNOWFLAKE_SCHEMA",
        "CLICKHOUSE_HOST",
        "CLICKHOUSE_DB",
        "CLICKHOUSE_PORT",
        "CLICKHOUSE_USER",
        "CLICKHOUSE_PASSWORD",
        "DQ_GOOGLE_CREDENTIAL",
    ]
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables for licensed notebooks: {', '.join(missing)}"
        )


def add_and_validate_target_args(parser):
    """
    Add the --target argument to the parser, parse args, and validate that at least one group is provided.
    If the 'licensed' group is present, ensure required environment variables are set.
    Returns the parsed args object.
    Exits with error if no valid target is provided or if required env vars are missing.
    """
    parser.add_argument(
        "--target",
        nargs="*",
        required=True,
        help="Comma-separated list of group names to target (e.g. --target=default,licensed,long-running)",
    )
    args = parser.parse_args()

    # Validate --target argument: must have at least one non-empty group
    targets_provided = args.target is not None
    targets_nonempty = (
        any(t.strip() != "" for t in args.target) if args.target else False
    )
    if not targets_provided or not targets_nonempty:
        print("Error: You must specify at least one group for --target.")
        sys.exit(2)

    # Normalize and check for 'licensed' group
    normalized_targets = []
    for arg in args.target:
        for part in arg.split(","):
            normalized = part.strip().lower().replace(" ", "-")
            if normalized:
                normalized_targets.append(normalized)
    if "licensed" in normalized_targets:
        set_licensed_env_vars()

    return args
