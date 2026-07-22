import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langchain_core.language_models import BaseChatModel

from app.catalog.router import router as catalog_router
from app.catalog.service import (
    CatalogNotFoundError,
    CatalogValidationError,
    register_pending_research_provider,
)
from app.chat import service as chat_service
from app.chat.router import router as chat_router
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.profile.router import router as profile_router
from app.profile.service import ProfileNotFoundError, ProfileValidationError
from app.research import service as research_service
from app.research.executor import BackgroundResearchExecutor
from app.research.provider import GeminiSearchProvider
from app.research.router import router as research_router
from app.research.service import ResearchNotFoundError, ResearchValidationError

logger = logging.getLogger(__name__)


def _build_chat_model(settings: Settings) -> BaseChatModel | None:
    """The chat LLM, or None when no Gemini key is resolvable — the chat endpoint
    then answers 503 while the rest of the API keeps working."""
    api_key = (
        settings.gemini_api_key
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    if not api_key:
        logger.warning("no Gemini API key configured; chat is disabled")
        return None
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model=settings.chat_model, api_key=api_key)


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
        chat_service.configure_chat_model(_build_chat_model(settings))
        yield
        chat_service.configure_chat_model(None)
        research_service.configure_dispatcher(None)
        executor.shutdown()

    app = FastAPI(title="motoCompare API", version="0.1.0", lifespan=lifespan)
    app.include_router(catalog_router, prefix="/api/catalog", tags=["catalog"])
    app.include_router(research_router, prefix="/api/research", tags=["research"])
    # Profile paths live directly under /api (/api/profile, /api/garage, /api/dream-bikes).
    app.include_router(profile_router, prefix="/api", tags=["profile"])
    app.include_router(chat_router, prefix="/api/chat", tags=["chat"])

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
