# ruff: noqa: UP007
# Pydantic evaluates type annotations at runtime which does not support `|`.

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Annotated, Optional, Union

from pydantic import (
    AliasChoices,
    Field,
    PostgresDsn,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Hold all the configuration properties of the app, not only the ones related to Atoti.

    See https://pydantic-docs.helpmanual.io/usage/settings/.
    """

    model_config = SettingsConfigDict(frozen=True)

    data_refresh_period: Optional[timedelta] = timedelta(minutes=1)

    aws_s3_path: str = "s3://data.atoti.io/notebooks/french-presidential-election-2022/"

    # The $PORT environment variable is used by most PaaS to indicate the port the app server should bind to.
    port: int = 9091

    requests_timeout: timedelta = timedelta(seconds=30)
    user_content_storage: Annotated[
        Optional[Union[PostgresDsn, Path]],
        Field(
            # $DATABASE_URL is used by some PaaS such to designate the URL of the app's primary database.
            # For instance: https://devcenter.heroku.com/articles/heroku-postgresql#designating-a-primary-database.
            validation_alias=AliasChoices("user_content_storage", "database_url")
        ),
    ] = Path("content")
