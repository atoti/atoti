from __future__ import annotations

import os

# Doing this before any import of `atoti`.
# Setting the variable using `os.environ` instead of pytest's `MonkeyPatch` so that the change happens before pytest evaluates other modules.
os.environ["ATOTI_HIDE_EULA_MESSAGE"] = str(True)
