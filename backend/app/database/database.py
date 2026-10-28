import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker, declarative_base

_repository_root = Path(__file__).resolve().parents[3]
_backend_root = Path(__file__).resolve().parents[2]
_env_file = next(
    (
        path
        for path in (_repository_root / ".env", _backend_root / ".env")
        if path.is_file()
    ),
    None,
)
if _env_file is not None:
    load_dotenv(_env_file)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the project .env file")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        try:
            db.close()
        except DBAPIError as error:
            # FastAPI may run yield-dependency cleanup after the response has
            # already been sent. A disconnect during connection release must
            # not trigger a second error response after response start.
            print(
                "Database session cleanup error | "
                f"error_type={type(error).__name__}"
            )
