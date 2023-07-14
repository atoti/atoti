from __future__ import annotations

import sys
from pathlib import Path
from app.create_users import create_users

import atoti as tt

from .config import Config
from .create_and_join_tables import create_and_join_tables
from .create_cubes import create_cubes
from .load_tables import load_tables


def create_session(*, config: Config) -> tt.Session:
    user_content_storage: Path | tt.UserContentStorageConfig | None = None

    if config.user_content_storage is not None:
        user_content_storage = (
            config.user_content_storage
            if isinstance(config.user_content_storage, Path)
            else tt.UserContentStorageConfig(url=str(config.user_content_storage))
        )
    return tt.Session(
        authentication=tt.BasicAuthenticationConfig(),
        logging=tt.LoggingConfig(destination=sys.stdout),
        port=config.port,
        user_content_storage=user_content_storage,
    )


def start_session(*, config: Config) -> tt.Session:
    """Start the session, declare the data model and load the initial data."""
    session = create_session(config=config)
    create_users(session)
    create_and_join_tables(session)
    create_cubes(session)
    load_tables(session, config=config)
    return session
