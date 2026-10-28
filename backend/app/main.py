import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import OperationalError

from app.api.document_routes import router as document_router
from app.api.excel_routes import router as excel_router
from app.api.export_routes import router as export_router
from app.api.standards_routes import router as standards_router

logger = logging.getLogger("app")

API_PREFIX = "/api/v1"
LOCAL_ORIGIN_REGEX = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"


def configure_logging() -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def configured_origins() -> list[str]:
    return [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]


configure_logging()

app = FastAPI(title="Standards Intelligence Backend")


@app.get("/", include_in_schema=False)
async def root():
    """Send browsers that open the API host to the interactive docs."""
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(OperationalError)
async def handle_database_operational_error(
    request: Request,
    error: OperationalError,
):
    """Report database connection/query failures as service unavailable."""
    logger.exception(
        "Database operational error | path=%s | error_type=%s",
        request.url.path,
        type(error.orig).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "The standards database is currently unavailable. "
                "Check the database network or VPN connection, then retry."
            )
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, error: Exception):
    """Hide internal failures from clients and record them for operators."""
    logger.exception("Unhandled error | path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins(),
    allow_origin_regex=LOCAL_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    standards_router,
    excel_router,
    export_router,
    document_router,
):
    app.include_router(router, prefix=API_PREFIX)