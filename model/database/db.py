"""
Database initialization and session management.
"""

import os
from sqlalchemy import create_engine
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

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    """Yield a fresh session per request. FastAPI Depends() ensures one session
    per request lifecycle — no scoped_session needed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
