from pathlib import Path
import glob
import os
from typing import List, Optional, Union


def get_excluded_notebook_groups(
    exclusion_file: str = "tests/test_exclusion.txt",
) -> dict:
    """
    Parse the exclusion file and return a dictionary mapping group names to lists of excluded notebook paths.
    Each group is defined by a header line (e.g., # ---GroupName---), followed by notebook paths.
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


def get_target_notebooks(
    include: Optional[Union[str, List[str]]] = None,
) -> List[str]:
    """
    Determine which notebooks should be included for testing.

    Args:
        include: Group name or list of group names to include (from the exclusion file). If None, returns all notebooks not excluded by any group (the default set).

    Returns:
        Sorted list of notebook paths to include.
    """
    notebook_paths = get_all_notebook_paths()
    exclusion_groups = get_excluded_notebook_groups()

    # If include is None, return all notebooks minus any exclusions (default set)
    if include is None:
        # Collect all exclusions from all groups
        all_exclusions = set()
        for group_paths in exclusion_groups.values():
            all_exclusions.update(group_paths)
        # Separate exclusions into files and directories
        excluded_files = {p for p in all_exclusions if p.endswith(".ipynb")}
        excluded_dirs = {
            p.rstrip("/") for p in all_exclusions if not p.endswith(".ipynb")
        }

        def is_excluded(nb_path: str) -> bool:
            return nb_path in excluded_files or any(
                nb_path.startswith(d + "/") for d in excluded_dirs
            )

        return sorted([nb for nb in notebook_paths if not is_excluded(nb)])

    # Otherwise, return notebooks explicitly included from specified groups
    if isinstance(include, (list, tuple, set)):
        include_groups = set(include)
    elif include:
        include_groups = {include}
    else:
        include_groups = set()

    group_notebooks = []
    for group in include_groups:
        for nb in exclusion_groups.get(group, []):
            if nb in notebook_paths and nb not in group_notebooks:
                group_notebooks.append(nb)
    return sorted(group_notebooks)
