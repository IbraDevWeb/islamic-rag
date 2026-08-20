from __future__ import annotations

import asyncio

import asyncpg

from app.core.config import settings
from app.db.migrations import apply_migrations


async def _main() -> None:
    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        applied = await apply_migrations(conn)
    finally:
        await conn.close()

    if applied:
        print("Applied migrations: " + ", ".join(applied))
    else:
        print("Database schema is already up to date.")


if __name__ == "__main__":
    asyncio.run(_main())
