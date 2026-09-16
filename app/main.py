from fastapi import FastAPI

from app.api.category import router as category_router
from app.api.product import router as product_router
from app.api.image import router as image_router
from app.api.ai_generation import router as ai_generation_router
from app.api.search import router as search_router
from app.api.rag import router as rag_router
from app.api.recommendation import router as recommendation_router
from app.core.config import settings
from fastapi.staticfiles import StaticFiles

import app.models

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.include_router(category_router)
app.include_router(product_router)
app.include_router(image_router)
app.include_router(ai_generation_router)
app.include_router(search_router)
app.include_router(rag_router)
app.include_router(recommendation_router)

app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)

@app.get("/")
def root():
    return {
        "message": settings.app_name,
        "debug": settings.debug
    }