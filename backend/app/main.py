from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.catalog.router import router as catalog_router
from app.catalog.service import (
    CatalogNotFoundError,
    CatalogValidationError,
    register_pending_research_provider,
)
from app.config import get_settings
from app.db import SessionLocal
from app.profile.router import router as profile_router
from app.profile.service import ProfileNotFoundError, ProfileValidationError
from app.research import service as research_service
from app.research.executor import BackgroundResearchExecutor
from app.research.provider import GeminiSearchProvider
from app.research.router import router as research_router
from app.research.service import ResearchNotFoundError, ResearchValidationError


def create_app() -> FastAPI:
    settings = get_settings()
    executor = BackgroundResearchExecutor(
        SessionLocal,
        GeminiSearchProvider(
            api_key=settings.gemini_api_key,
            model=settings.research_model,
        ),
        max_attempts=settings.research_max_attempts,
        conflict_tolerance=settings.research_conflict_tolerance,
        max_workers=settings.research_workers,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        research_service.configure_dispatcher(executor)
        register_pending_research_provider(research_service.pending_research_for_bike)
        yield
        research_service.configure_dispatcher(None)
        executor.shutdown()

    app = FastAPI(title="motoCompare API", version="0.1.0", lifespan=lifespan)
    app.include_router(catalog_router, prefix="/api/catalog", tags=["catalog"])
    app.include_router(research_router, prefix="/api/research", tags=["research"])
    # Profile paths live directly under /api (/api/profile, /api/garage, /api/dream-bikes).
    app.include_router(profile_router, prefix="/api", tags=["profile"])

    @app.exception_handler(CatalogNotFoundError)
    def handle_not_found(request: Request, error: CatalogNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(CatalogValidationError)
    def handle_validation(request: Request, error: CatalogValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(ResearchNotFoundError)
    def handle_research_not_found(
        request: Request, error: ResearchNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ResearchValidationError)
    def handle_research_validation(
        request: Request, error: ResearchValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(ProfileNotFoundError)
    def handle_profile_not_found(
        request: Request, error: ProfileNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ProfileValidationError)
    def handle_profile_validation(
        request: Request, error: ProfileValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
