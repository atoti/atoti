from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import requests
from pydantic import HttpUrl


def read_json(
    base_path: HttpUrl | Path, file_path: Path, /, *, timeout: timedelta
) -> object:
    if isinstance(base_path, Path):
        return json.loads((base_path / file_path).read_bytes())

    url = f"{base_path}/{file_path.as_posix()}"
    response = requests.get(url, timeout=timeout.total_seconds())
    response.raise_for_status()
    return response.json()
