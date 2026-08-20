import asyncpg
import httpx
from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/dependencies")
async def dependencies_health() -> dict[str, object]:
    checks: dict[str, dict[str, str]] = {}

    try:
        conn = await asyncpg.connect(settings.postgres_dsn)
        try:
            value = await conn.fetchval("SELECT 1")
            checks["postgres"] = {
                "status": "ok" if value == 1 else "error",
            }
        finally:
            await conn.close()
    except Exception as exc:
        checks["postgres"] = {
            "status": "error",
            "detail": exc.__class__.__name__,
        }

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.qdrant_url}/healthz")
            response.raise_for_status()
        checks["qdrant"] = {"status": "ok"}
    except Exception as exc:
        checks["qdrant"] = {
            "status": "error",
            "detail": exc.__class__.__name__,
        }

    overall = (
        "ok"
        if all(check["status"] == "ok" for check in checks.values())
        else "degraded"
    )

    return {
        "status": overall,
        "services": checks,
    }
