from __future__ import annotations

import atoti as tt


def create_users(session: tt.Session, /) -> None:
    session.security.basic.credentials["user"] = "user"
    session.security.individual_roles["user"] = {"ROLE_USER"}
    print(f"User created with roles: {session.security.individual_roles['user']}")

    session.security.basic.credentials["tt_admin"] = "tt_admin"
    session.security.individual_roles["tt_admin"] = {"ROLE_ADMIN", "ROLE_USER"}
    print(f"Admin created with roles: {session.security.individual_roles['tt_admin']}")
