from __future__ import annotations

from typing import Annotated

import typer

from ._get_executable_path import get_executable_path
from ._run_command import run_command

_APP_PACKAGE = "app"
_PACKAGES = (_APP_PACKAGE, "cli", "tests")

_CheckOption = Annotated[bool, typer.Option("--check/--fix")]

app = typer.Typer()


@app.command(help="Build the Docker image.")
def build_docker(tag: str) -> None:
    run_command(
        [get_executable_path("docker"), "build", "--tag", tag, "."],
        env={"DOCKER_BUILDKIT": "1"},
    )


@app.command(help="Format the project files.")
def format(*, check: _CheckOption = False) -> None:  # noqa: A001
    run_command(["black", *(["--check"] if check else []), "."], run_with_poetry=True)


@app.command(help="Lint the project files.")
def lint(*, check: _CheckOption = False) -> None:
    run_command(
        ["ruff", "check", ".", *([] if check else ["--fix"])], run_with_poetry=True
    )


@app.command(help="Start the app.")
def start() -> None:
    run_command(["python", "-u", "-m", _APP_PACKAGE], run_with_poetry=True)


@app.command(help="Run the test suite.")
def test() -> None:
    run_command(["pytest", "--capture=no"], run_with_poetry=True)


@app.command(help="Statically check the Python types.")
def typecheck() -> None:
    run_command(
        [
            "mypy",
            *[arg for package in _PACKAGES for arg in ["--package", package]],
        ],
        run_with_poetry=True,
    )
