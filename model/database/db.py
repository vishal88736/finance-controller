"""
Database initialization and session management.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from .models import Base

DB_PATH = os.environ.get("DATABASE_URL", "sqlite:///./finance_controller.db")
# Fix sqlite URL format if relative path is given
if DB_PATH.startswith("sqlite:///") and not DB_PATH.startswith("sqlite:////"):
    # Ensure current working directory has DB
    pass

engine = create_engine(
    DB_PATH,
    connect_args={"check_same_thread": False} if "sqlite" in DB_PATH else {},
    echo=False
)

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
