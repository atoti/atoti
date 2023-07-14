from __future__ import annotations

from functools import cache
from shutil import which


@cache
def get_executable_path(name: str, /) -> str:
    path = which(name)
    if not path:
        raise RuntimeError(f"Could not get path to `{name}` binary.")
    return path
