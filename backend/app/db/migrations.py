from __future__ import annotations

from pathlib import Path

import asyncpg


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def apply_migrations(conn: asyncpg.Connection) -> list[str]:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    applied_rows = await conn.fetch("SELECT version FROM schema_migrations")
    applied = {row["version"] for row in applied_rows}
    newly_applied: list[str] = []

    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = path.stem
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO schema_migrations(version) VALUES($1)", version
            )
        newly_applied.append(version)

    return newly_applied
