from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from app.api.standards_routes import router as standards_router
from app.api.excel_routes import router as excel_router
from app.api.export_routes import router as export_router
from app.api.document_routes import router as document_router


app = FastAPI(
    title="Standards Intelligence Backend"
)


@app.get("/", include_in_schema=False)
async def root():
    """Send browsers that open the API host to the interactive docs."""
    return RedirectResponse(url="/docs")


@app.exception_handler(OperationalError)
async def handle_database_operational_error(
    request: Request,
    error: OperationalError,
):
    """Report database connection/query failures as service unavailable."""
    print(
        "Database operational error | "
        f"path={request.url.path} | "
        f"error_type={type(error.orig).__name__}"
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


app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(standards_router)
app.include_router(excel_router)
app.include_router(export_router)
app.include_router(document_router)
