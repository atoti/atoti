from pathlib import Path
import glob
import os


def get_excluded_notebooks(exclusion_file="tests/test_exclusion.txt"):
    """
    Read the exclusion file and return a set of excluded notebook paths and directories.
    Ignores empty lines and comment lines (starting with '#').
    All paths are normalized to use forward slashes.
    """
    exclusion_path = Path(exclusion_file)
    exclusions = set()
    if exclusion_path.exists():
        with exclusion_path.open() as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                exclusions.add(line.replace("\\", "/"))
    return exclusions


def get_all_notebook_paths():
    """
    Return a list of all notebook paths in the project, normalized as relative paths with forward slashes.
    """
    return [
        os.path.relpath(nb_path, ".").replace("\\", "/")
        for nb_path in glob.glob("./*/**/*.ipynb", recursive=True)
        if "ipynb_checkpoints" not in nb_path
    ]


def get_included_notebooks():
    """
    Return a sorted list of all notebook paths, with exclusions applied.
    Exclusions are read from the test_exclusion.txt file and can be either files or directories.
    """
    notebook_paths = get_all_notebook_paths()
    exclusions = get_excluded_notebooks()
    excluded_files = {p for p in exclusions if p.endswith(".ipynb")}
    excluded_dirs = {p.rstrip("/") for p in exclusions if not p.endswith(".ipynb")}

    def should_exclude(nb):
        if nb in excluded_files:
            return True
        return any(nb.startswith(d + "/") for d in excluded_dirs)

    included = [nb for nb in notebook_paths if not should_exclude(nb)]
    included.sort()
    return included
