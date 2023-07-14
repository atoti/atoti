from __future__ import annotations

from collections.abc import Mapping, Sequence
from shlex import join
from subprocess import run

import typer

from ._get_executable_path import get_executable_path


def run_command(
    command: Sequence[str],
    /,
    *,
    env: Mapping[str, str] | None = None,
    run_with_poetry: bool = False,
) -> None:
    if run_with_poetry:
        command = [get_executable_path("poetry"), "run", *command]

    typer.echo(f"$ {join(command)}", err=True)
    run(command, check=True, env=env)  # noqa: S603
