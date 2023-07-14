from __future__ import annotations

from urllib.parse import urlencode, urlparse

from pydantic import PostgresDsn, TypeAdapter


def normalize_postgres_dsn_for_atoti_sql(url: PostgresDsn, /) -> PostgresDsn:
    parts = urlparse(str(url))

    parts = parts._replace(scheme="postgresql")

    query_parts: list[str] = []

    if parts.query:
        query_parts.append(parts.query)

    if parts.username or parts.password:
        query_parts.append(
            urlencode({"user": parts.username, "password": parts.password})
        )
        # Remove username and password.
        parts = parts._replace(netloc=parts.netloc.split("@", maxsplit=1).pop())

    if query_parts:
        parts = parts._replace(query="&".join(query_parts))

    new_url = parts.geturl()
    return TypeAdapter(PostgresDsn).validate_python(new_url)
