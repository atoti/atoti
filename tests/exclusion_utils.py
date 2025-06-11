from pathlib import Path
import glob
import os


def get_excluded_notebook_groups(exclusion_file="tests/test_exclusion.txt"):
    """
    Parse the exclusion file and return a dictionary mapping group headers to lists of excluded notebook paths.
    - Group headers are lines like '# --- Group Name ---'.
    - Ignores empty lines and comment lines (starting with '#').
    - All paths are normalized to use forward slashes.
    """
    exclusion_path = Path(exclusion_file)
    groups = {}
    current_group = None
    if exclusion_path.exists():
        with exclusion_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("# ---") and line.endswith("---"):
                    # Extract group name from header
                    current_group = line.strip("# -").strip()
                    groups[current_group] = []
                elif line.startswith("#"):
                    continue  # skip other comments
                else:
                    if current_group is None:
                        current_group = "Ungrouped"
                        groups.setdefault(current_group, [])
                    # Normalize path
                    groups[current_group].append(line.replace("\\", "/"))
    return groups


def get_all_notebook_paths():
    """
    Return a list of all notebook paths in the project, as relative paths with forward slashes.
    Excludes any paths containing 'ipynb_checkpoints'.
    """
    notebook_files = glob.glob("./*/**/*.ipynb", recursive=True)
    return [
        os.path.relpath(nb_path, ".").replace("\\", "/")
        for nb_path in notebook_files
        if "ipynb_checkpoints" not in nb_path
    ]


def get_included_notebooks(keep=None):
    """
    Return a sorted list of all notebook paths, with exclusions applied.
    - If 'keep' is provided (string or list), those group(s) are included in the result.
    - Exclusions are read from the test_exclusion.txt file and can be either files or directories.
    """
    notebook_paths = get_all_notebook_paths()
    exclusion_groups = get_excluded_notebook_groups()

    # Support multiple groups to keep
    keep_groups = set()
    if keep is not None:
        if isinstance(keep, (list, tuple, set)):
            keep_groups = set(keep)
        else:
            keep_groups = {keep}

    # Collect all exclusions except those in keep_groups
    all_exclusions = set()
    for group, group_paths in exclusion_groups.items():
        if group in keep_groups:
            continue
        all_exclusions.update(group_paths)

    # Split exclusions into files and directories
    excluded_files = {p for p in all_exclusions if p.endswith(".ipynb")}
    excluded_dirs = {p.rstrip("/") for p in all_exclusions if not p.endswith(".ipynb")}

    def should_exclude(nb_path):
        if nb_path in excluded_files:
            return True
        return any(nb_path.startswith(d + "/") for d in excluded_dirs)

    # Filter out excluded notebooks
    included = [nb for nb in notebook_paths if not should_exclude(nb)]

    # Add back any notebooks from keep_groups (if they exist and aren't already included)
    for group in keep_groups:
        for nb in exclusion_groups.get(group, []):
            if nb in notebook_paths and nb not in included:
                included.append(nb)

    included.sort()
    return included
