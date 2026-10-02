import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# 1. Determine connection string:
# Priority 1: Cloud/Remote DATABASE_URL (MySQL, Postgres, etc.)
# Priority 2: Local MySQL credentials (if DB_PASSWORD provided in .env)
# Priority 3: Zero-config SQLite database file (data/app.db) for instant cloud deployment
if settings.database_url:
    db_url_str = settings.database_url
    if db_url_str.startswith("mysql://"):
        db_url_str = db_url_str.replace("mysql://", "mysql+pymysql://", 1)
    DATABASE_URL = db_url_str
elif settings.db_password:
    DATABASE_URL = URL.create(
        drivername="mysql+pymysql",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )
else:
    os.makedirs("data", exist_ok=True)
    DATABASE_URL = "sqlite:///./data/app.db"

# 2. Engine configuration
engine_kwargs = {}
if str(DATABASE_URL).startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_recycle": settings.db_pool_recycle,
        "pool_timeout": settings.db_pool_timeout,
    })

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)