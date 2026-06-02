from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Fallback to local SQLite database if no database URL is set
db_url = settings.database_url or "sqlite:///./reservbot.db"

# Handle SQLite specifically (needs check_same_thread disablement)
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(db_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """
    Dependency helper to provide a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
