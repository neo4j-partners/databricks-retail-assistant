"""API route registration."""

from fastapi import APIRouter

from sample_agent.routes.chat import router as chat_router
from sample_agent.routes.health import router as health_router
from sample_agent.routes.memory import router as memory_router
from sample_agent.routes.products import router as products_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(chat_router)
api_router.include_router(memory_router)
api_router.include_router(products_router)

__all__ = ["api_router"]
