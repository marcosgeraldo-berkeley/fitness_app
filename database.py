"""
Database configuration for PostgreSQL
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database URL from environment
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://fitplan_user:fitplan_pass@localhost:5432/fitplan_db'
)

# Create engine
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    echo=False  # Set to True for SQL query logging
)

# Create session factory
SessionLocal = scoped_session(sessionmaker(bind=engine))

# Base class for models
Base = declarative_base()

def get_db():
    """
    Get database session
    Usage in Flask routes:
        db = get_db()
        try:
            # Use db here
            db.commit()
        except:
            db.rollback()
            raise
        finally:
            db.close()
    """
    return SessionLocal()

def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)

def close_db():
    """Close database session"""
    SessionLocal.remove()