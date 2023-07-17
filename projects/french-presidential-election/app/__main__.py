from __future__ import annotations

import logging

from . import App, Config

config = Config()

with App(config=config) as app:
    logging.info("Session listening on port %s", app.session.port)
    app.session.wait()
