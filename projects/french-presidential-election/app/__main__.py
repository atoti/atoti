from __future__ import annotations

from . import App, Config

config = Config()

with App(config=config) as app:
    print(f"Session listening on port {app.session.port}")  # noqa: T201
    app.session.wait()
