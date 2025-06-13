from pathlib import Path
import glob
import os
from typing import List, Optional, Union


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


def get_target_notebooks(
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
        # Default: all notebooks minus any group exclusions
        all_exclusions = set(nb for group in exclusion_groups.values() for nb in group)
        excluded_files = {p for p in all_exclusions if p.endswith(".ipynb")}
        excluded_dirs = {
            p.rstrip("/") for p in all_exclusions if not p.endswith(".ipynb")
        }

        def is_excluded(notebook_path: str) -> bool:
            return notebook_path in excluded_files or any(
                notebook_path.startswith(d + "/") for d in excluded_dirs
            )

        return sorted(nb for nb in notebook_paths if not is_excluded(nb))

    # Only include notebooks from specified groups
    include_groups = (
        set(include_only)
        if isinstance(include_only, (list, tuple, set))
        else {include_only}
    )
    group_notebooks = set()
    for group in include_groups:
        for nb in exclusion_groups.get(group, []):
            if nb in notebook_paths:
                group_notebooks.add(nb)
    return sorted(group_notebooks)
