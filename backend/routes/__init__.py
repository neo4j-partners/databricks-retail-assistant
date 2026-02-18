"""API route registration."""

from fastapi import APIRouter

from backend.routes.chat import router as chat_router
from backend.routes.health import router as health_router
from backend.routes.memory import router as memory_router
from backend.routes.products import router as products_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(chat_router)
api_router.include_router(memory_router)
api_router.include_router(products_router)

__all__ = ["api_router"]
