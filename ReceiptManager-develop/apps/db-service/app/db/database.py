import os
from app.core.logger import get_logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

logger = get_logger(__name__)

DATABASE_HOST = os.getenv(
    "DB_HOST",
    "postgres",
)

DATABASE_PORT = os.getenv(
    "DB_PORT",
    "5432",
)

DATABASE_NAME = os.getenv(
    "POSTGRES_DB",
    "name",
)

DATABASE_USER = os.getenv(
    "POSTGRES_USER",
    "postgres",
)

DATABASE_PASSWORD = os.getenv(
    "POSTGRES_PASSWORD",
    "postgres",
)

DATABASE_URL = f"postgresql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
