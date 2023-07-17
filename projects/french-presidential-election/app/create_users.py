from __future__ import annotations

import logging

import atoti as tt


def create_users(session: tt.Session, /) -> None:
    session.security.basic.credentials["user"] = "user"
    session.security.individual_roles["user"] = {"ROLE_USER"}
    logging.info(
        "User created with roles: %s", session.security.individual_roles["user"]
    )

    session.security.basic.credentials["tt_admin"] = "tt_admin"
    session.security.individual_roles["tt_admin"] = {"ROLE_ADMIN", "ROLE_USER"}
    logging.info(
        "Admin created with roles: %s", session.security.individual_roles["tt_admin"]
    )
