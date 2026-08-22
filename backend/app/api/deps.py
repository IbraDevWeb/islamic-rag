from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
from fastapi import HTTPException, status

from app.core.config import settings


async def get_postgres_connection() -> AsyncIterator[asyncpg.Connection]:
    """Yield one PostgreSQL connection and always close it after the request.

    This dependency is intentionally isolated so tests can override it and a
    connection pool can replace it later without changing route contracts.
    """

    try:
        conn = await asyncpg.connect(settings.postgres_dsn)
    except (OSError, asyncpg.PostgresError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL is unavailable",
        ) from exc

    try:
        yield conn
    finally:
        await conn.close()
