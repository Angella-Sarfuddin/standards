from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.standards_routes import router as standards_router
from app.routes.excel_routes import router as excel_router
from app.routes.export_routes import router as export_router
from app.routes.document_routes import router as document_router
from app.routes.export_routes import router as export_router


app = FastAPI(
    title="Standards Intelligence Backend"
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
app.include_router(export_router)