"""
Database configuration for PostgreSQL
"""
import os, json
# import boto3
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv
from db_schema import DATABASE_SCHEMA
from urllib.parse import quote_plus, urlencode, urlparse, urlunparse, parse_qsl
import logging

# Load environment variables
load_dotenv()

# Set up logger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database URL from environment
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://fitplan_user:fitplan_pass@postgres:5432/fitplan_db'
)

def get_db_creds():
    # Local path: one JSON env var
    js = os.getenv("DATABASE_SECRET_JSON")
    
    if js:
        logger.info("Loading database credentials from JSON environment variable.")
        logger.info(f"DATABASE_SECRET_JSON: {js}")
        return json.loads(js)

    # AWS path: fetch secret by ARN
    arn = os.getenv("DATABASE_SECRET_ARN")
    if arn:
        return json.loads(arn)

    # Fallback: read split vars (useful for quick tests)
    return {
        "username": os.getenv("POSTGRES_USER", "fitplan_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "fitplan_pass"),
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "fitplan_db"),
    }

def add_params(url, **extra):
    u = urlparse(url); q = dict(parse_qsl(u.query)); q.update(extra)
    return urlunparse(u._replace(query=urlencode(q)))

creds = get_db_creds()

# creds from your existing get_db_creds()
user = quote_plus(creds["username"])       # quote in case of special chars
pwd  = quote_plus(creds["password"])
host = creds["host"]; port = creds["port"]; db = creds["dbname"]

base_url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"

# Decide whether to require SSL
# - If DATABASE_SECRET_ARN is present, assume production and require SSL
# - OR if explicitly forced via FORCE_LOCAL_SSL=true (useful when you do local TLS)
force_ssl = bool(os.getenv("DATABASE_SECRET_ARN")) or os.getenv("FORCE_LOCAL_SSL", "false").lower() in ("1", "true", "yes")

if force_ssl:
    conn_str = add_params(base_url, sslmode="require")
    connection_args = {"sslmode": "require"}
else:
    conn_str = base_url
    connection_args = {}
connection_args["connect_timeout"] = 5  # fail fast while testing # TODO: extend this for production


# Create engine
engine = create_engine(
    conn_str,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    connect_args=connection_args,
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
