from fastapi import APIRouter

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.dungeons import router as dungeon_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.imports import router as imports_router
from app.api.v1.routes.personnel import router as personnel_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(dungeon_router, tags=["dungeons"])
api_router.include_router(imports_router, prefix="/imports/characters", tags=["imports"])
api_router.include_router(personnel_router, tags=["personnel"])
