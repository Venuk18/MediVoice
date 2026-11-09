import os
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings, normalize_database_url

db_url = normalize_database_url(settings.DATABASE_URL)

# Engine configuration for SQLite vs PostgreSQL connection pooling
connect_args = {}
pool_kwargs = {}
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    pool_kwargs = {
        "pool_size": int(os.getenv("DATABASE_POOL_SIZE", "20")),
        "max_overflow": int(os.getenv("DATABASE_MAX_OVERFLOW", "30")),
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }

engine = create_engine(
    db_url,
    echo=False,
    connect_args=connect_args,
    **pool_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency that provides an independent SQLAlchemy session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
