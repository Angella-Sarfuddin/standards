from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from app.routes.standards_routes import router as standards_router
from app.routes.excel_routes import router as excel_router
from app.routes.export_routes import router as export_router
from app.routes.document_routes import router as document_router


app = FastAPI(
    title="Standards Intelligence Backend"
)


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
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(standards_router)
app.include_router(excel_router)
app.include_router(export_router)
app.include_router(document_router)
