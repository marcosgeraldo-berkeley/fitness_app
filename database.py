"""
Database configuration for PostgreSQL
"""
import os, json
import boto3
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv
from db_schema import DATABASE_SCHEMA

# Load environment variables
load_dotenv()

# Database URL from environment
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://fitplan_user:fitplan_pass@localhost:5432/fitplan_db'
)

def get_db_creds():
    # Local path: one JSON env var
    js = os.getenv("DATABASE_SECRET_JSON")
    if js:
        return json.loads(js)

    # AWS path: fetch secret by ARN
    arn = os.getenv("DATABASE_SECRET_ARN")
    if arn:
        sm = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))
        sec = sm.get_secret_value(SecretId=arn)
        return json.loads(sec["SecretString"])

    # Fallback: read split vars (useful for quick tests)
    return {
        "username": os.getenv("POSTGRES_USER", "fitplan_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "fitplan_pass"),
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "fitplan_db"),
    }

creds = get_db_creds()
conn_str = (
    f"postgresql+psycopg2://{creds['username']}:{creds['password']}"
    f"@{creds['host']}:{creds['port']}/{creds['dbname']}"
)
# engine = create_engine(conn_str, pool_pre_ping=True)
# print(conn_str)

# Create engine
engine = create_engine(
    conn_str,
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
    with engine.begin() as connection:
        for table_name, definition in DATABASE_SCHEMA.items():
            connection.execute(text(definition["create"]))
            for column_sql in definition.get("columns", {}).values():
                connection.execute(text(column_sql))
            for statement in definition.get("indexes", []):
                connection.execute(text(statement))

def close_db():
    """Close database session"""
    SessionLocal.remove()

def get_engine():
    """Get the SQLAlchemy engine"""
    return engine
