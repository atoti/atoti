from __future__ import annotations

from types import TracebackType

import atoti as tt

from .config import Config
from .start_session import start_session


class App:
    """Regroup the session with other resources so that they can be closed together."""

    def __init__(self, *, config: Config) -> None:
        # The config is kept private to deter passing an App to functions when a Config is all they need.
        self._session = start_session(config=config)

    @property
    def session(self) -> tt.Session:
        return self._session

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> App:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
