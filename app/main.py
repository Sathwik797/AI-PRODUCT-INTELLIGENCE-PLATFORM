from fastapi import FastAPI

from app.api.category import router as category_router
from app.api.product import router as product_router
from app.api.image import router as image_router
from app.core.config import settings
from app.db.base import Base
from app.db.database import engine

import app.models

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.include_router(category_router)
app.include_router(product_router)
app.include_router(image_router)

@app.get("/")
def root():
    return {
        "message": settings.app_name,
        "debug": settings.debug
    }