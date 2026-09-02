from fastapi import APIRouter

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.dungeons import router as dungeon_router
from app.api.v1.routes.edit_locks import router as edit_locks_router
from app.api.v1.routes.editor import router as editor_router
from app.api.v1.routes.generation import router as generation_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.imports import router as imports_router
from app.api.v1.routes.personnel import router as personnel_router
from app.api.v1.routes.publication import router as publication_router
from app.api.v1.routes.rule_sets import router as rule_sets_router
from app.api.v1.routes.schedules import router as schedules_router
from app.api.v1.routes.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(editor_router, tags=["schedule-editor"])
api_router.include_router(edit_locks_router, tags=["schedule-edit-locks"])
api_router.include_router(publication_router, tags=["schedule-publication"])
api_router.include_router(generation_router, tags=["generation"])
api_router.include_router(rule_sets_router, tags=["schedule-rules"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(dungeon_router, tags=["dungeons"])
api_router.include_router(imports_router, prefix="/imports/characters", tags=["imports"])
api_router.include_router(personnel_router, tags=["personnel"])
api_router.include_router(schedules_router, prefix="/schedules", tags=["schedules"])
api_router.include_router(users_router, tags=["users"])
