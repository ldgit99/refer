"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router as api_router
from app.capabilities import document_capabilities
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="refer — academic citation review",
    version=__version__,
    description="Multi-agent review of in-text citations and references for DOCX/HWP/HWPX papers.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict[str, object]:
    """Liveness probe used by CI and the deployment platform."""
    return {
        "status": "ok",
        "version": __version__,
        "llm_enabled": settings.llm_enabled,
        "llm_provider": settings.active_llm_provider,
        "formats": document_capabilities(),
    }


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs"}
