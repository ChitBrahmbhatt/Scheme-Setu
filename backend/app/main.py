"""FastAPI app entrypoint (BACKEND_BRIEF.md Step 5).

Stateless, no database. Data is loaded once at startup via app.loader; the
service must serve every endpoint except /assist/* with LLM_ENABLED=false
and no API key present.
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.errors import ApiError, error_envelope
from app.loader import get_data
from app.routers import calculate, partners, recommend, reference

app = FastAPI(title="Sarathi API", version="2026.09.10")

STATIC_DIR = Path(__file__).resolve().parent / "static"

app.include_router(recommend.router, prefix="/api/v1")
app.include_router(calculate.router, prefix="/api/v1")
app.include_router(partners.router, prefix="/api/v1")
app.include_router(reference.router, prefix="/api/v1")


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_envelope(exc.code, exc.message, exc.field))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0]
    loc = [str(part) for part in first_error["loc"] if part != "body"]
    field = ".".join(loc) if loc else None
    return JSONResponse(
        status_code=400,
        content=error_envelope("VALIDATION_ERROR", first_error["msg"], field),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_envelope("INTERNAL", "An unexpected error occurred.", None),
    )


@app.get("/dev", include_in_schema=False)
def dev_console() -> FileResponse:
    """Plain-HTML/vanilla-JS backend dev console (BACKEND_BRIEF.md Step 8).
    Development/QA tool only — not the production frontend. It is only a
    client for the real API; no business logic is duplicated here."""
    return FileResponse(STATIC_DIR / "dev.html")


@app.get("/api/v1/health")
def health() -> dict:
    data = get_data()
    settings = get_settings()
    return {
        "status": "ok",
        "ruleset_version": data.schemes.ruleset_version,
        "llm_enabled": settings.llm_enabled,
        "schemes_loaded": len(data.schemes.schemes),
        "partners_loaded": len(data.partners.partners),
    }
