from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.catalog.router import router as catalog_router
from app.catalog.service import CatalogNotFoundError, CatalogValidationError


def create_app() -> FastAPI:
    app = FastAPI(title="motoCompare API", version="0.1.0")
    app.include_router(catalog_router, prefix="/api/catalog", tags=["catalog"])

    @app.exception_handler(CatalogNotFoundError)
    def handle_not_found(request: Request, error: CatalogNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(CatalogValidationError)
    def handle_validation(request: Request, error: CatalogValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
