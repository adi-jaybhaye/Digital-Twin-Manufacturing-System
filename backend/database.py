"""
database.py
-----------
Database connection setup using SQLAlchemy.

Uses MySQL via PyMySQL driver.
Falls back to SQLite if MySQL connection fails — useful for development
without a MySQL server running.

NOTE: Set proper credentials in the .env file (see .env.example).
"""

import os
from pathlib import Path
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables from .env file
# Search up from this file's directory so .env is found when running from backend/
_env_path = Path(__file__).parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path)

# ─── Build Database URL ───────────────────────────────────────────────

MYSQL_HOST     = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT     = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER     = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "digital_twin_mfg")

encoded_password = quote_plus(MYSQL_PASSWORD)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"mysql+pymysql://{MYSQL_USER}:{encoded_password}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)

if os.getenv("VERCEL"):
    SQLITE_FALLBACK_FILE = Path("/tmp") / "digital_twin_dev.db"
else:
    SQLITE_FALLBACK_FILE = Path(__file__).parent / "digital_twin_dev.db"

SQLITE_FALLBACK_URL = f"sqlite:///{SQLITE_FALLBACK_FILE.as_posix()}"

Base = declarative_base()

# ─── Engine Creation with Fallback ───────────────────────────────────

def create_db_engine():
    """
    Try to connect to MySQL. If it fails, fall back to SQLite.
    SQLite fallback is useful for development/demo without a MySQL server.
    """
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
        # Test the connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[OK] Connected to MySQL database: {MYSQL_DATABASE}")
        return engine, "mysql"
    except Exception as e:
        print(f"[WARNING] MySQL connection failed: {e}")
        print(f"[WARNING] Falling back to SQLite: {SQLITE_FALLBACK_URL}")
        engine = create_engine(
            SQLITE_FALLBACK_URL,
            connect_args={"check_same_thread": False},
            echo=False,
        )
        return engine, "sqlite"


engine, db_type = create_db_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    FastAPI dependency: yields a database session.
    Usage: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables defined in models."""
    try:
        from models import db_models  # when run from backend/ directory
    except ImportError:
        try:
            from backend.models import db_models  # when run from project root
        except ImportError:
            pass  # models already imported elsewhere
    Base.metadata.create_all(bind=engine)
    print("[OK] Database tables created/verified")
