from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

if settings.database_url:
    db_url_str = settings.database_url
    if db_url_str.startswith("mysql://"):
        db_url_str = db_url_str.replace("mysql://", "mysql+pymysql://", 1)
    DATABASE_URL = db_url_str
else:
    DATABASE_URL = URL.create(
        drivername="mysql+pymysql",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle,
    pool_timeout=settings.db_pool_timeout,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)