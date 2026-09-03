"""
Database initialization and session management.
"""

import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from .models import Base

DB_PATH = os.environ.get("DATABASE_URL", "sqlite:///./finance_controller.db")

engine = create_engine(
    DB_PATH,
    connect_args={"check_same_thread": False, "timeout": 30.0} if "sqlite" in DB_PATH else {},
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Lightweight additive migrations: columns added to a schema after the fact must
# be applied to pre-existing SQLite databases, since `create_all` only creates
# missing tables, not missing columns.
_SQLITE_MIGRATIONS = [
    ("cash_forecast_results", "baseline_source", "VARCHAR"),
    ("documents", "document_role", "VARCHAR"),
    ("documents", "role_confidence", "FLOAT"),
    ("documents", "role_reason", "TEXT"),
]


def init_db():
    Base.metadata.create_all(bind=engine)
    if "sqlite" in DB_PATH:
        _apply_sqlite_migrations()


def _apply_sqlite_migrations():
    inspector = inspect(engine)
    with engine.begin() as conn:
        existing_tables = set(inspector.get_table_names())
        for table, column, coltype in _SQLITE_MIGRATIONS:
            if table not in existing_tables:
                continue
            cols = {c["name"] for c in inspector.get_columns(table)}
            if column not in cols:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {coltype}'))

def get_db():
    """Yield a fresh session per request. FastAPI Depends() ensures one session
    per request lifecycle — no scoped_session needed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
