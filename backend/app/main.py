from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.search import router as search_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description=(
        "API du prototype Islamic RAG. "
        "Le LLM n'est jamais considéré comme une source. "
        "Les routes de retrieval renvoient des passages traçables vers leurs sources."
    ),
)

app.include_router(health_router)
app.include_router(search_router)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "environment": settings.app_env,
        "docs": "/docs",
    }
