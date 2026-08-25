from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.routes.evidence import router as evidence_router
from app.api.routes.evidence_bundle import router as evidence_bundle_router
from app.api.routes.health import router as health_router
from app.api.routes.search import router as search_router
from app.api.routes.synthesis import router as synthesis_router
from app.core.config import settings


class UTF8JSONResponse(JSONResponse):
    """Make UTF-8 explicit for older HTTP clients such as Windows PowerShell 5.1."""

    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title=settings.app_name,
    version="0.9.0",
    default_response_class=UTF8JSONResponse,
    description=(
        "API du prototype Islamic RAG. "
        "Le LLM n'est jamais considéré comme une source. "
        "Les routes de retrieval renvoient des passages traçables vers leurs sources."
    ),
)

app.include_router(health_router)
app.include_router(search_router)
app.include_router(evidence_router)
app.include_router(evidence_bundle_router)
app.include_router(synthesis_router)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "environment": settings.app_env,
        "docs": "/docs",
    }
